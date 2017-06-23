#script (python)

#
# IMPORTS
#

import clingo
import controller
from src.utils import printer
from src.utils import utils

#
# DEFINES
#

# nodes and control
START         = "START"
START_LOOP    = "START_LOOP"
SOLVE         = "SOLVE"
SAT           = "SAT"
UNSAT         = "UNSAT"
UNKNOWN       = "UNKNOWN"
END_LOOP      = "END_LOOP"
END           = "END"
SATISFIABLE   = "SATISFIABLE"
UNSATISFIABLE = "UNSATISFIABLE"

# strings
STR_ANSWER             = "Answer: {}"
STR_OPTIMUM_FOUND      = "OPTIMUM FOUND"
STR_OPTIMUM_FOUND_STAR = "OPTIMUM FOUND *"
STR_UNSATISFIABLE      = "UNSATISFIABLE"
# program names
#ENCODINGS        = os.path.dirname(os.path.realpath(__file__)) + "/encodings.lp"
DO_HOLDS_AT_ZERO = "do_holds_at_zero"
DO_HOLDS         = "do_holds"
OPEN_HOLDS       = "open_holds"
VOLATILE_FACT    = "volatile_fact"
VOLATILE_EXT     = "volatile_external"
DELETE_MODEL     = "delete_model"
UNSAT_PRG        = "unsat"
NOT_UNSAT_PRG    = "not_unsat"
PPROGRAM         = utils.PPROGRAM
PBASE            = utils.PBASE
APPROX           = utils.APPROX

# predicate and term names
VOLATILE      = utils.VOLATILE
MODEL         = utils.MODEL
HOLDS         = utils.HOLDS
VOLATILE      = utils.VOLATILE
UNSAT_ATOM    = utils.UNSAT
HOLDS_AT_ZERO = "holds_at_zero"
CSP           = "$"

# exceptions
SAME_MODEL = """\
same stable model computed twice, there is an error in the input, \
probably an incorrect preference program"""

#
# AUXILIARY PROGRAMS
#

token    = "##"
programs = \
  [(DO_HOLDS_AT_ZERO,       [],"""
#show ##holds_at_zero(X) : ##""" + HOLDS + """(X,0)."""),
   (DO_HOLDS,            ["m"],"""
##""" + HOLDS + """(X,m) :- X = @getHolds()."""),
   (OPEN_HOLDS,          ["m"],"""
{ ##""" + HOLDS + """(X,m) } :- X = @getHolds().  
{ ##""" + HOLDS + """(X,m) } :- X = @getNHolds()."""),
   (VOLATILE_FACT, ["m1","m2"],"""
##""" + VOLATILE + """(##m(m1),##m(m2))."""),
   (VOLATILE_EXT,  ["m1","m2"],"""
#external ##""" + VOLATILE + """(##m(m1),##m(m2))."""),
   (DELETE_MODEL,           [],"""
:-     ##""" + HOLDS + """(X,0) : X = @getHolds(); 
   not ##""" + HOLDS + """(X,0) : X = @getNHolds()."""),
   (UNSAT_PRG,     ["m1","m2"],"""
:- not ##""" + UNSAT_ATOM + """(##m(m1),##m(m2)),
       ##""" +   VOLATILE + """(##m(m1),##m(m2))."""),
   (NOT_UNSAT_PRG, ["m1","m2"],"""
:-     ##""" + UNSAT_ATOM + """(##m(m1),##m(m2)),
       ##""" +   VOLATILE + """(##m(m1),##m(m2)).""")
  ]



#
# Auxiliary Classes (EndException, State)
#

class EndException(Exception):
    pass

class State:
    pass

def call(object, method):
    if object:
        getattr(object, method)()

#
# Solver
#

class Solver:

    def __init__(self, control):
        # parameters
        self.control           = control
        self.underscores       = utils.underscores
        # strings
        self.volatile_str      = self.underscores + VOLATILE
        self.model_str         = self.underscores + MODEL
        self.holds_at_zero_str = self.underscores + HOLDS_AT_ZERO
        self.holds_str         = self.underscores + HOLDS
        # holds
        self.holds             = []
        self.nholds            = []
        # others
        self.state             = State()
        self.state.max_models  = 1
        self.state.old_holds   = None
        self.state.old_nholds  = None
        self.shown             = []
        self.solving_result    = None
        #l = [START, START_LOOP, SOLVE, SAT, UNSAT, UNKNOWN, END_LOOP, END]
        # self.pre  = dict([(i, []) for i in l])
        # self.post = dict([(i, []) for i in l])
        self.externals = dict()
        self.improving = []
        # printer
        self.printer = printer.Printer()

    #
    # AUXILIARY
    #
    def get_external(self, m1, m2):
        external = self.externals.get((m1,m2))
        if external is None:
            f1 = clingo.Function(self.model_str, [int(m1)])
            f2 = clingo.Function(self.model_str, [int(m2)])
            external = clingo.Function(self.volatile_str, [f1, f2])
            self.externals[(m1,m2)] = external
        return external

    def getHolds(self):
        return self.holds
    
    def getNHolds(self):
        return self.nholds

    def head(self, atuple):
        try:
            return atuple.arguments[0]
        except:
            return atuple

    def second(self, atuple):
        try:
            return atuple.arguments[1]
        except:
            return atuple

    def __cat(self, tuple):
        if tuple.arguments:
            return "".join([str(i) for i in tuple.arguments]).replace('"',"")
        else:
            return str(tuple)

    #
    # CLINGO PROXY
    #


    def add_encodings(self):
        for i in programs:
            self.control.add(i[0], i[1], i[2].replace(token, self.underscores))
        self.control.ground([(DO_HOLDS_AT_ZERO, [])], self)


    def ground_approximation(self):
        self.control.ground([(APPROX, [])], self)


    def ground_preference_base(self):
        self.control.ground([(PBASE, [])], self)


    def ground_holds(self):
        control, prev_step = self.control, self.state.step-1
        control.ground([(DO_HOLDS, [prev_step])], self)


    def ground_preference_program(self):
        state, control, prev_step = self.state, self.control, self.state.step-1
        #control.ground([(DO_HOLDS,       [prev_step]),
        control.ground([(PPROGRAM,      [0,prev_step]),
                        (NOT_UNSAT_PRG, [0,prev_step]),
                        (VOLATILE_EXT,  [0,prev_step])],self)
        control.assign_external(self.get_external(0,prev_step),True)
        self.improving.append(prev_step)


    #TODO: move to program_parser when translation improved
    def check_errors(self):
        # get preference program errors
        pr, control, u = self.printer, self.control, self.underscores
        error = False
        for atom in control.symbolic_atoms.by_signature(u+"_error", 1):
            string = "\n" + self.__cat(atom.symbol.arguments[0])
            pr.print_spec_error(string)
            error = True
        if error:
            pr.do_print("")
            raise Exception("parsing failed")


    def on_model(self, model):
        self.holds, self.nholds, self.shown = [], [], []
        for a in model.symbols(shown=True):
            if a.name == self.holds_at_zero_str:
                self.holds.append(a.arguments[0])
            else:
                self.shown.append(a)
        #TODO: improve on nholds, we do not need it always
        for a in model.symbols(terms=True, complement=True):
            if a.name == self.holds_at_zero_str:
                self.nholds.append(a.arguments[0])


    def solve(self):
        result = self.control.solve(on_model=self.on_model)
        self.solving_result = None
        if result.satisfiable:
            self.solving_result = SATISFIABLE
        elif result.unsatisfiable:
            self.solving_result = UNSATISFIABLE

    def solve_unsat(self):
        self.solving_result = UNSATISFIABLE

    def __symbol2str(self,symbol):
        if symbol.name == CSP:
            return str(symbol.arguments[0]) + "=" + str(symbol.arguments[1])
        return str(symbol)


    def print_shown(self):
        self.printer.do_print(STR_ANSWER.format(self.state.models))
        self.printer.do_print(" ".join(map(self.__symbol2str, self.shown)))


    def print_optimum_string(self):
        self.printer.do_print(STR_OPTIMUM_FOUND)


    def print_unsat(self):
        self.printer.do_print(STR_UNSATISFIABLE)


    def check_last_model(self):
        if self.state.old_holds  == self.holds and (
           self.state.old_nholds == self.nholds):
                self.printer.do_print()
                raise Exception(SAME_MODEL)
        self.state.old_holds  = self.holds
        self.state.old_nholds = self.nholds


    def relax_previous_model(self):
        state, control = self.state, self.control
        control.release_external(self.get_external(0,state.step-1))


    def same_shown(self):
        if set(self.old_shown) == set(self.shown):
            self.enumerate_flag = True
            return True
        return False


    def same_shown_underscores(self):
        u = self.underscores
        s1 = set([i for i in self.old_shown if not str(i).startswith(u)])
        s2 = set([i for i in     self.shown if not str(i).startswith(u)])
        if s1 == s2:
            self.enumerate_flag = True
            return True
        return False


    def on_model_enumerate(self,model):
        true = model.symbols(shown=True)
        self.shown = [ i for i in true if i.name != self.holds_at_zero_str ]
        # self.state.same_shown_function is modified by EnumerationController 
        # at controller.py
        if self.enumerate_flag or not self.state.same_shown_function():
            self.state.models     += 1
            self.state.opt_models += 1
            self.print_shown()
            self.printer.do_print(STR_OPTIMUM_FOUND_STAR)


    def enumerate(self):
        # models
        control    = self.control
        old_models = self.control.configuration.solve.models
        if self.state.max_models == 0: 
            control.configuration.solve.models = 0
        else:
            control.configuration.solve.models = (self.state.max_models -
                                                  self.state.opt_models)
        # assumptions
        h = self.holds_str
        ass  = [ (clingo.Function(h, [x,0]), True)  for x in self.holds ]
        ass += [ (clingo.Function(h, [x,0]), False) for x in self.nholds]
        # solve
        self.old_shown, self.enumerate_flag = self.shown, False
        control.solve(ass, self.on_model_enumerate)
        self.shown = self.old_shown
        control.configuration.solve.models = old_models


    def relax_previous_models(self):
        state, control = self.state, self.control
        #for i in range(state.start_step,state.step):
        for i in self.improving:
            control.release_external(self.get_external(0, i))
        self.improving = []


    def handle_optimal_models(self):
        state, control, prev_step = self.state, self.control, self.state.step-1
        preference   = [(PPROGRAM,      [prev_step,0])]
        unsat        = [(UNSAT_PRG,     [prev_step,0])]
        delete_model = [(DELETE_MODEL,             [])]
        volatile     = [(VOLATILE_FACT, [prev_step,0])]
        control.ground(preference + unsat + delete_model + volatile,self)


    def end(self):
        state, p = self.state, self.printer
        p.print_stats(self.control, state.models, state.more_models,
                      state.opt_models,state.stats)
        raise EndException


    #
    # OPTIONS
    #

    def set_options(self,options):
        for key,value in options.items():
            setattr(self.state,key,value)


    #
    # RUN()
    #


    def run(self):

        # controllers
        general = controller.GeneralController(self, self.state)
        optimal = controller.GeneralControllerHandleOptimal(self, self.state)
        basic = controller.BasicMethodController(self, self.state)
        if self.state.solving_mode == "approx":
            approx = controller.ApproxMethodController(self, self.state)
        else:
            approx = None
        enumeration = controller.EnumerationController(self, self.state)
        checker = controller.CheckerController(self, self.state)

        # loop
        try:
            # START
            general.start()
            call(approx, "start")
            self.printer.do_print("Solving...")
            while True:
                # START_LOOP
                general.start_loop()
                basic.start_loop()
                checker.start_loop()
                # SOLVE
                call(approx, "solve")
                general.solve()
                if self.solving_result == SATISFIABLE:
                    # SAT
                    general.sat()
                elif self.solving_result == UNSATISFIABLE:
                    # UNSAT
                    general.unsat()
                    basic.unsat()
                    enumeration.unsat()
                    optimal.unsat()
                    # UNSAT_POST
                    general.unsat_post()
                else:
                    # UNKNOWN
                    pass
                # END_LOOP
                general.end_loop()
        except RuntimeError as e: 
            self.printer.print_error("ERROR (clingo): {}".format(e))
        except EndException as e: 
            # END
            pass


