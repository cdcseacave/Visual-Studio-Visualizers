# seacave_formatters.py
import lldb

# ---------------------------------------------------
# Summary: "{{size=X capacity=Y}}"
# ---------------------------------------------------
def cList_summary(valobj, internal_dict):
    raw = valobj.GetNonSyntheticValue()
    size = raw.GetChildMemberWithName("_size").GetValueAsUnsigned()
    cap = raw.GetChildMemberWithName("_vectorSize").GetValueAsUnsigned()
    return f"{{size={size} capacity={cap}}}"

# ---------------------------------------------------
# Synthetic children: elements from _vector[0.._size)
# ---------------------------------------------------
class cListSyntheticProvider:
    def __init__(self, valobj, internal_dict):
        self.valobj = valobj
        self.update()

    def update(self):
        # extract members once
        self.size_obj   = self.valobj.GetChildMemberWithName("_size")
        self.vector_obj = self.valobj.GetChildMemberWithName("_vector")
        self.size = self.size_obj.GetValueAsUnsigned()
        self.elem_type = self.vector_obj.GetType().GetPointeeType()
        self.elem_size = self.elem_type.GetByteSize()

    def num_children(self):
        return int(self.size)

    def get_child_at_index(self, index):
        if index < 0 or index >= self.size:
            return None
        # Create a synthetic element at offset = index * sizeof(T)
        try:
            return self.vector_obj.CreateChildAtOffset(
                f"[{index}]",
                index * self.elem_size,
                self.elem_type
            )
        except:
            return None

    def get_child_index(self, name):
        try:
            # LLDB calls children “0”, “1”, ...
            return int(name)
        except:
            return -1

# ---------------------------------------------------
# Registration (handles template types)
# ---------------------------------------------------
def __lldb_init_module(debugger, internal_dict):
    debugger.HandleCommand(
        'type summary add -F seacave_formatters.cList_summary -e -x "^SEACAVE::cList<.*>$"'
    )
    debugger.HandleCommand(
        'type synthetic add -l seacave_formatters.cListSyntheticProvider -x "^SEACAVE::cList<.*>$"'
    )
