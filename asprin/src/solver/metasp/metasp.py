# MIT License
#
# Copyright (c) 2017 Javier Romero
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
# -*- coding: utf-8 -*-


#
# IMPORTS
#

import clingo
import subprocess
import tempfile
import re
from . import meta_programs
from . import scc
from ...utils import utils


#
# DEFINES
#

U_METAPREF = utils.U_METAPREF
U_METABASE = utils.U_METABASE
PREFERENCE = utils.PREFERENCE
OPTIMIZE   = utils.OPTIMIZE

CLINGO = "clingo"
REIFY_OUTPUT = "--output=reify"
VERSION = "--version"
NO_CLINGO = "clingo binary version not found (when running 'clingo --version')"
OLD_CLINGO = "clingo binary too old (when running 'clingo --version') version 5.3 or newer is needed"

METAPREF_BASIC = """
{ ##holds(X,0..1) } :- X = @get_holds_domain().
##volatile(##m(0),##m(1)).
:- ##unsat(##m(0),##m(1)).
#show ##holds/2.
#const ##m1=0.
#const ##m2=1.
"""

BINDING_A = """
**true(atom(A)) :-     ##holds(X,0), **output(##holds(X,1),A).           % from base
**fail(atom(A)) :- not ##holds(X,0), **output(##holds(X,1),A).           % from base
**true(atom(A)) :- $$true(atom(B)), $$output_term(##holds_at_zero(X),B), % from meta_base
                   **output(##holds(X,0),A).
**fail(atom(A)) :- $$fail(atom(B)), $$output_term(##holds_at_zero(X),B), % from meta_base
                   **output(##holds(X,0),A).
**bot :- $$bot.
$$bot :- **bot.
:- not **bot.
"""

BINDING_B = """
**true(atom(A)) :-     ##holds(X,0), **output(##holds(X,1),B), **literal_tuple(B,A).  % from base
**fail(atom(A)) :- not ##holds(X,0), **output(##holds(X,1),B), **literal_tuple(B,A).  % from base
**true(atom(A)) :- $$true(atom(B)), $$output(##holds(X,0),BB), $$literal_tuple(BB,B), % from meta_base
                   **output(##holds(X,0),C), **literal_tuple(C,A).
**fail(atom(A)) :- $$fail(atom(B)), $$output(##holds(X,0),BB), $$literal_tuple(BB,B), % from meta_base
                   **output(##holds(X,0),C), **literal_tuple(C,A).
**bot :- $$bot.
$$bot :- **bot.
:- not **bot.
"""

# get_holds_domain() should not be defined here
ASPRIN_LIBRARY_PY = """
#script(python)

import math

def exp2(x):
    return int(math.pow(2,x.number))

def get(atuple, index):
    try:
        return atuple.arguments[index.number]
    except:
        return atuple

def get_mode():
    return 'normal'

sequences = {}
def get_sequence(name, elem):
    string = str(name)
    if string in sequences:
        sequences[string] += 1
    else:
        sequences[string]  = 1
    return sequences[string]

def length(atuple):
    try:
        return len(atuple.arguments)
    except:
        return 1 

def log2up(x):
    return int(math.ceil(math.log(x.number,2)))

#end.
"""

HOLDS_DOMAIN_PY = """
import clingo
holds_domain = {}
def get_holds_domain():
    return holds_domain
"""

class Observer:

    def __init__(
        self,
        control,
        register_observer = False,
        replace = False,
        bool_add_statement = False,
        bool_add_base = False,
        bool_add_specification = False,
        bool_add_constants_nb = False
    ):
        # flags
        self.bool_add_statement     = bool_add_statement
        self.bool_add_base          = bool_add_base
        self.bool_add_specification = bool_add_specification
        self.bool_add_constants_nb  = bool_add_constants_nb
        if register_observer:
            control.register_observer(self, replace)
        # observations
        self.rules = []
        self.weight_rules = []
        self.output_atoms = []
        self.output_terms = []
        self.statements = []
        self.base = None           # (program, old constants, new constants)
        self.specification = None  # (program, old constants, new constants)
        self.constants_nb = None   # (program,            [],            [])

    #
    # control object observer
    #

    def rule(self, choice, head, body):
        self.rules.append((choice, head, body))

    def weight_rule(self, choice, head, lower_bound, body):
        self.weight_rules.append((choice, head, lower_bound, body))

    def output_atom(self, symbol, atom):
        self.output_atoms.append((symbol, atom))

    def output_term(self, symbol, condition):
        self.output_terms.append((symbol, condition))

    #
    # program parser observer
    #

    def add_statement(self, statement):
        if self.bool_add_statement:
            self.statements.append(statement)

    def add_base(self, program, old, new):
        if self.bool_add_base:
            self.base = (program, old, new)

    def add_specification(self, program, old, new):
        if self.bool_add_specification:
            self.specification = (program, old, new)

    def add_constants_nb(self, program, old, new):
        if self.bool_add_constants_nb:
            self.constants_nb = (program, old, new)


# abstract class
class AbstractMetasp:

    def __init__(self, solver):
        # uses solver.control, solver.observer and solver.underscores
        self.solver = solver

    # to be defined by subclasses
    def get_meta_program(self):
        return None

    #
    # get_pref() (used by MetaspPython and MetaspBinary)
    #

    def statement_to_str(self, statement):
        if str(statement.type) == "Definition": # to avoid printing [default]
            return "#const {}={}.".format(statement.name, statement.value)
        elif str(statement.type) == "Program":
            return "" # IMPORTANT: program statements are skipped
        return str(statement)

    def get_specification(self):
        underscores = self.solver.underscores
        signatures = [(underscores + PREFERENCE, 2),
                      (underscores + PREFERENCE, 5),
                      (underscores +   OPTIMIZE, 1)]
        symbolic_atoms = self.solver.control.symbolic_atoms
        spec = ""
        for name, arity in signatures:
            spec += " ".join([
                str(atom.symbol) + "."
                for atom in symbolic_atoms.by_signature(name, arity)
            ]) + "\n"
        return spec

    def get_pref(self):
        # basic program
        basic = METAPREF_BASIC.replace("##", self.solver.underscores)
        # preference specification
        specification = self.get_specification()
        # preference program
        preference_program = "\n".join([
            self.statement_to_str(s) for s in self.solver.observer.statements
        ])
        # constants
        constants = self.solver.observer.constants_nb[0]
        # return
        return basic + specification + preference_program + constants

    #
    # get_meta_bind() (used by MetaspPython and MetaspBinary)
    #

    def get_meta_bind(self, binding):
        out = binding.replace("##", self.solver.underscores)
        prefix_base = self.solver.underscores + "_"*U_METABASE
        prefix_pref = self.solver.underscores + "_"*U_METAPREF
        return out.replace("$$", prefix_base).replace("**", prefix_pref)


# Uses the observer in Python
class MetaspPython(AbstractMetasp):

    def __init__(self, solver):
        AbstractMetasp.__init__(self, solver)

    def get_meta_program(self):
        prefix = self.solver.underscores + "_"*U_METABASE
        meta_base = self.get_meta_from_observer(self.solver.observer, prefix)
        meta_pref = self.get_meta_pref()
        meta_bind = self.get_meta_bind(BINDING_A)
        return meta_base + meta_pref + meta_bind

    def get_meta_pref(self):
        ctl = clingo.Control([])
        observer = Observer(ctl, register_observer=True, replace=True)
        ctl.add("base", [], self.get_pref())
        ctl.ground([("base",[])], self.solver)
        prefix = self.solver.underscores + "_"*U_METAPREF
        return self.get_meta_from_observer(observer, prefix)

    # TODO: Implement option where we take care about repeated heads and bodies
    def get_meta_from_observer(self, observer, prefix=""):

        # start
        out = ""
        literal_tuple, wliteral_tuple, atom_tuple = 1, 1, 1
        p = prefix

        # fact 0
        # out += "% fact 0\n"
        out += "{}rule(disjunction(0),normal(0)). {}atom_tuple(0,0). {}literal_tuple(0).\n\n".format(p, p, p)

        # start graph
        graph = scc.Graph()

        # normal rules
        for choice, head, body in observer.rules:

            # out += "% normal rule\n"
            # body
            out += "{}literal_tuple({}).".format(p, literal_tuple) + "\n"
            out += " ".join(["{}literal_tuple({},{}).".format(p, literal_tuple, l) for l in body]) + "\n"
            # head
            head_type = "choice" if choice else "disjunction"
            out += "{}rule({}({}),normal({})).".format(p, head_type, atom_tuple, literal_tuple) + "\n"
            out += " ".join(["{}atom_tuple({},{}).".format(p, atom_tuple, l) for l in head]) + "\n\n"
            # update counters
            literal_tuple += 1
            atom_tuple += 1
            # update graph (this can be interwined with the rules above)
            for l in body:
                if l >= 0:
                    for atom in head:
                        graph.add_edge(atom, l)

        # weight rules
        for choice, head, lower_bound, body in observer.weight_rules:
            # out += "% weighted rule\n"
            # body
            out += " ".join(["{}weighted_literal_tuple({},{},{}).".format(p, wliteral_tuple, l, w) for l, w in body]) + "\n"
            # head
            head_type = "choice" if choice else "disjunction"
            out += "{}rule({}({}),sum({},{})).".format(p, head_type, atom_tuple, wliteral_tuple, lower_bound) + "\n"
            out += " ".join(["{}atom_tuple({},{}).".format(p, atom_tuple, l) for l in head]) + "\n\n"
            # update counters
            wliteral_tuple += 1
            atom_tuple += 1
            # update graph (this can be interwined with the rules above)
            for l, w in body:
                if l >= 0:
                    for atom in head:
                        graph.add_edge(atom, l)

        # sccs
        # out += "% sccs\n"
        out += graph.reify_sccs(p) + "\n"

        # output atoms
        # out += "% output atoms\n"
        for symbol, atom in observer.output_atoms:
            out += "{}output({},{}).\n".format(p, symbol, atom)

        # output terms
        # out += "% output term\n"
        for symbol, condition in observer.output_terms:
            out += "{}output_term({},{}).\n".format(p, symbol, condition[0])

        return out + meta_programs.metaD_program.replace("##", p)


# Uses clingo binary
class MetaspBinary(AbstractMetasp):

    def __init__(self, solver):
        AbstractMetasp.__init__(self, solver)
        self.check_clingo_version()

    def check_clingo_version(self):
        version = self.run_command([CLINGO, VERSION])
        match = re.match(r'clingo version (\d+)\.(\d+)', version)
        if match:
            first  = int(match.group(1))
            second = int(match.group(2))
            if first > 5 or (first == 5 and second >= 3):
                return
            raise Exception(OLD_CLINGO)
        raise Exception(NO_CLINGO)

    def get_meta_program(self):
        meta_base = self.get_meta_base()
        meta_pref = self.get_meta_pref()
        meta_bind = self.get_meta_bind(BINDING_B)
        return meta_base + meta_pref + meta_bind

    # WARNING:
    # The next function relies on the form of the specification programs,
    # assumes rules for preference/2, preference/5, optimize/1
    # start at the beginning of a line and finish at the end.
    # Depends on spec_parser/ast.py.
    def get_meta_base(self):
        observer = self.solver.observer
        # get base
        program  = observer.base[0] + "\n"
        # get specification without preference/2, /5 and optimize/1
        pattern = r'^(\_*)(' + PREFERENCE + r'|' + OPTIMIZE + r')'
        program += re.sub(
            pattern, r'%\1\2', observer.specification[0], flags=re.M
        ) + "\n"
        # add constants
        for idx, old in enumerate(observer.base[1]): # for every old constant
            program += "#const {}={}.".format(old, observer.base[2][idx]) + "\n"
        # add show
        program += "#show " + self.solver.underscores + "holds/2.\n"
        # get meta using clingo binary
        prefix = self.solver.underscores + "_"*U_METABASE
        return self.get_meta_using_binary(program, prefix)

    def get_meta_pref(self):
        holds_domain = ",\n".join(
            ['  clingo.parse_term("""{}""")'.format(x) for x in self.solver.holds_domain]
        )
        get_holds_domain = HOLDS_DOMAIN_PY.format("[\n" + holds_domain + "\n]")
        library = ASPRIN_LIBRARY_PY.replace("#end.", get_holds_domain + "\n#end.")
        prefix = self.solver.underscores + "_"*U_METAPREF
        return self.get_meta_using_binary(self.get_pref() + library, prefix)

    #
    # get_meta_using_binary()
    #

    # run command and return stdout as a string
    def run_command(self, command):
        with tempfile.TemporaryFile() as file_out:
            # execute clingo
            subprocess.call(command, stdout=file_out)
            # read output
            file_out.seek(0)
            output = file_out.read()
        if isinstance(output, bytes):
            output = output.decode()
        return output

    def get_meta_using_binary(self, program, prefix):
        with tempfile.NamedTemporaryFile() as file_in:
            # write program to file_in
            file_in.write(program.encode())
            file_in.flush()
            # run command
            command = [CLINGO, REIFY_OUTPUT, file_in.name]
            output = self.run_command(command)
        # add prefix and return
        output = re.sub(r'^(\w+)', r'' + prefix + r'\1', output, flags=re.M)
        output += meta_programs.metaD_program.replace("##", prefix)
        return output

# REDO
def run(base, metaD=False):

    # observe rules
    ctl = clingo.Control(["0"])
    #observer = Observer(ctl, False)
    observer = Observer(ctl, True)
    ctl.add("base", [], base)
    ctl.ground([("base", [])])
    #models0 = []
    #with ctl.solve(yield_=True) as handle:
    #    for m in handle:
    #        models0.append(" ".join(sorted([str(x) for x in m.symbols(shown=True)])))
    #    # print(handle.get())
    #models0 = sorted(models0)

    # use reified version
    base = observer.reify()
    print(base)
    return
    if metaD:
        base += meta_programs.metaD_program
    else:
        base += meta_programs.meta_program
    ctl = clingo.Control(["0"])
    ctl.add("base", [], base)
    ctl.ground([("base", [])])
    models1 = []
    with ctl.solve(yield_=True) as handle:
        for m in handle:
            models1.append(" ".join(sorted([str(x) for x in m.symbols(shown=True)])))
        # print(handle.get())
    models1 = sorted(models1)

   # check and print
    print("ERROR" if models0 != models1 else "OK")
    if models0 != models1:
        print(models0)
        print(models1)
    if len(models0):
        models0[0] += "_x "
        print("OK" if models0 != models1 else "ERROR")


#
# programs
#

basic = """
{a}. b.
"""

aggregates = """
{a(X) : dom(X)}.
b(X) :- X = { a(Y) }.
dom(1..2).
#show b/1.
"""

# pigeon hole
pigeon = """
#const n=6.
pigeon(1..n+1). box(1..n+1).
1 { in(X,Y) : box(Y) } 1 :- pigeon(X).
:- 2 { in(X,Y) : pigeon(X) },  box(Y).
a(X,Y,Z) :- in(X,Y), in(Y,Z).
"""

loop = """
a :- b.
b :- a.
b :- c.
a :- c.
{ c }.
"""

many_loops = """
dom(1..320).
{ edge(X,Y) : dom(X), dom(Y) }.
tr(X,Y) :- edge(X,Y).
tr(X,Y) :- tr(X,Z), tr(Z,Y).
:- tr(X,X).
"""
programs = [basic, aggregates, pigeon, loop, many_loops]
#programs = [""" a ; b :- 1 #sum {1:b; 1:c}. {c}."""]
programs = [many_loops]
if __name__ == "__main__":
    # meta
    for program in programs:
        print("##### META  #######")
        print(program)
        run(program)
        print("#####################")
    programs = []
    # metaD
    for program in programs:
        print("##### METAD #######")
        print(program)
        run(program, True)
        print("#####################")

