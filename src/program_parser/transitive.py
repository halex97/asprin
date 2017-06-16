from collections import namedtuple


Info = namedtuple('Info','key item')


class Node:

    def __init__(self, key, item):
        self.key  = key
        self.item = item
        self.next = set()
        self.prev = set()
        self.neg_next = set()
        self.neg_prev = set()
    
    def __str__(self):
        out = []
        if self.next:
            out += [(i.key, "+") for i in self.next]
        if self.neg_next:
            out += [(i.key, "-") for i in self.neg_next]
        ret = "#{}\n:{}\n".format(self.key, str(self.item))
        list = ["({},{},{})".format(self.key,i[0],i[1]) for i in out]
        return ret + "\n".join(list)
        

class TransitiveClosure:

    def __init__(self):
        self.nodes = {}

    # add set_1 to set_2, and delete set_1 from set_3
    def __update(self, set_1, set_2, set_3):
        set_2.update(set_1)
        set_3.difference_update(set_1)
  
    def map_items(self, f):
        for key, node in self.nodes.items():
            for i in node.item:
                if i:
                    f(i)

    # update graph with (Info) a
    def add_node(self, a):
        node = self.nodes.get(a.key)
        if not node:
            node = Node(a.key, [a.item])
            self.nodes[a.key] = node
        else:
            node.item.append(a.item)
        return node

    # add edge of type sign from (Info) a to (Info) b
    def add_edge(self, a, b, sign):
        
        # add nodes
        node_a = self.nodes[a.key]
        node_b = self.nodes[b.key]
        #node_a = self.add_node(a)
        #node_b = self.add_node(b)
        
        # next
        if sign:
            next = node_b.next.copy()
            next.add(node_b)
            node_a.next.update(next)
            for i in node_a.prev:
                i.next.update(next)
            for i in node_a.neg_prev:
                self.__update(next, i.neg_next, i.next)
        
        # neg_next
        if sign:
            neg_next = node_b.neg_next
        else:
            neg_next = node_b.neg_next.union(node_b.next)
            neg_next.add(node_b)
        if neg_next:
            self.__update(neg_next, node_a.neg_next, node_a.next)
            for i in node_a.prev:
                self.__update(neg_next, i.neg_next, i.next)
            for i in node_a.neg_prev:
                self.__update(neg_next, i.neg_next, i.next)
        
        # prev
        if sign:
            prev = node_a.prev.copy()
            prev.add(node_a)
            node_b.prev.update(prev)
            for i in node_b.next:
                i.prev.update(prev)
            for i in node_b.neg_next:
                self.__update(prev, i.neg_prev, i.prev)
        
        # neg_prev
        if sign:
            neg_prev = node_a.neg_prev
        else:
            neg_prev = node_a.neg_prev.union(node_a.prev)
            neg_prev.add(node_a)
        if neg_prev:
            self.__update(neg_prev, node_b.neg_prev, node_b.prev)
            for i in node_b.next:
                self.__update(neg_prev, i.neg_prev, i.prev)
            for i in node_a.neg_next:
                self.__update(neg_prev, i.neg_prev, i.prev)

    def __str__(self):
        out = ""
        for key, item in self.nodes.items():
            out += str(item) + "\n"
        return out

    def get_next(self, key):
        return [i.key for i in self.nodes[key].next]


if __name__ == "__main__":
    graph = [(1,2,True), (2,3,True), (3,4,False), (4,5,True), (5,5,True),
             (7,8,False), (8,7,False), (2,1,False)]#, (5,1,True)]
    tmp = []
    for i in range(1,2):
        for j in graph:
            tmp.append((j[0]*i,j[1]*i,j[2]))
    graph = tmp
    tc = TransitiveClosure()
    for i in graph:
        tc.add_edge(Info(i[0],i[0]),Info(i[1],i[1]),i[2])
    print tc

