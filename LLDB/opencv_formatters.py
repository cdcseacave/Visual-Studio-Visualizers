import lldb

def __lldb_init_module(debugger, internal_dict):
    # cv::Mat
    debugger.HandleCommand('type synthetic add -x "^cv::Mat$" --python-class opencv_formatters.CVMatSyntheticProvider')
    debugger.HandleCommand('type summary add -x "^cv::Mat$" --python-function opencv_formatters.CVMatSummaryProvider')
    
    # cv::Point, cv::Point3
    debugger.HandleCommand('type summary add -x "^cv::Point_<.>$" --python-function opencv_formatters.PointSummary')
    debugger.HandleCommand('type summary add -x "^cv::Point3_<.>$" --python-function opencv_formatters.Point3Summary')
    # Matches "TPoint2", "SEACAVE::TPoint2", "TPoint2<double>", etc.
    debugger.HandleCommand('type summary add -x "^.*TPoint2(<.+>)?$" --python-function opencv_formatters.PointSummary')
    # Matches "TPoint3", "SEACAVE::TPoint3", "TPoint3<double>", etc.
    debugger.HandleCommand('type summary add -x "^.*TPoint3(<.+>)?$" --python-function opencv_formatters.Point3Summary')

    # cv::Size
    debugger.HandleCommand('type summary add -x "^cv::Size_<.>$" --python-function opencv_formatters.SizeSummary')
    
    # cv::Rect
    debugger.HandleCommand('type summary add -x "^cv::Rect_<.>$" --python-function opencv_formatters.RectSummary')
    
    # cv::RotatedRect
    debugger.HandleCommand('type summary add -x "^cv::RotatedRect$" --python-function opencv_formatters.RotatedRectSummary')
    
    # cv::Range
    debugger.HandleCommand('type summary add -x "^cv::Range$" --python-function opencv_formatters.RangeSummary')

    # cv::Scalar, cv::Vec
    debugger.HandleCommand('type synthetic add -x "^cv::Scalar_<.>$" --python-class opencv_formatters.VecSyntheticProvider')
    debugger.HandleCommand('type synthetic add -x "^cv::Vec<.+>$" --python-class opencv_formatters.VecSyntheticProvider')
    
    # cv::Matx (Small fixed matrices)
    debugger.HandleCommand('type synthetic add -x "^cv::Matx<.+>$" --python-class opencv_formatters.MatxSyntheticProvider')
    debugger.HandleCommand('type summary add -x "^cv::Matx<.+>$" --python-function opencv_formatters.MatxSummary')
    # Matches "TMatrix", "SEACAVE::TMatrix", "TMatrix<double, 3, 3>", etc.
    debugger.HandleCommand('type synthetic add -x "^.*TMatrix<.+>$" --python-class opencv_formatters.MatxSyntheticProvider')
    debugger.HandleCommand('type summary add -x "^.*TMatrix<.+>$" --python-function opencv_formatters.MatxSummary')
    
    # cv::Ptr
    debugger.HandleCommand('type synthetic add -x "^cv::Ptr<.+>$" --python-class opencv_formatters.PtrSyntheticProvider')
    debugger.HandleCommand('type summary add -x "^cv::Ptr<.+>$" --python-function opencv_formatters.PtrSummary')

    # cv::AutoBuffer
    debugger.HandleCommand('type summary add -x "^cv::AutoBuffer<.+>$" --python-function opencv_formatters.AutoBufferSummary')
    debugger.HandleCommand('type synthetic add -x "^cv::AutoBuffer<.+>$" --python-class opencv_formatters.AutoBufferSyntheticProvider')

    # cv::Complex
    debugger.HandleCommand('type summary add -x "^cv::Complex<.+>$" --python-function opencv_formatters.ComplexSummary')

    # cv::Exception
    debugger.HandleCommand('type summary add -x "^cv::Exception$" --summary-string "${var.msg}"')

    print("OpenCV LLDB Formatters loaded.")

# ------------------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------------------
def get_member_val(valobj, name):
    x = valobj.GetChildMemberWithName(name)
    if x.IsValid():
        return x.GetValueAsUnsigned(0)
    return 0

def get_member_str(valobj, name):
    x = valobj.GetChildMemberWithName(name)
    if x.IsValid():
        return str(x.GetValue())
    return ""

# ------------------------------------------------------------------------------
# cv::Mat
# ------------------------------------------------------------------------------
class CVMatSyntheticProvider:
    def __init__(self, valobj, internal_dict):
        self.valobj = valobj
        self.rows = 0
        self.cols = 0
        self.flags = 0
        self.channels = 1
        self.depth_type = None
        self.data_ptr = None

    def update(self):
        self.rows = get_member_val(self.valobj, "rows")
        self.cols = get_member_val(self.valobj, "cols")
        self.flags = get_member_val(self.valobj, "flags")
        self.data_ptr = self.valobj.GetChildMemberWithName("data")
        
        # Decode flags
        # Depth: flags & 7
        depth = self.flags & 7
        # Channels: ((flags & 0xfff) >> 3) + 1
        self.channels = ((self.flags & 0xfff) >> 3) + 1

        types = {
            0: "uint8_t", 1: "int8_t", 2: "uint16_t", 3: "int16_t",
            4: "int32_t", 5: "float", 6: "double"
        }
        self.type_name = types.get(depth, "uint8_t") # default to uchar

    def num_children(self):
        return 5 # rows, cols, channels, type, data_view

    def get_child_index(self, name):
        if name == "rows": return 0
        if name == "cols": return 1
        if name == "channels": return 2
        if name == "type": return 3
        if name == "data": return 4
        return -1

    def get_child_at_index(self, index):
        if index == 0:
            return self.valobj.CreateValueFromExpression("rows", str(self.rows))
        if index == 1:
            return self.valobj.CreateValueFromExpression("cols", str(self.cols))
        if index == 2:
            return self.valobj.CreateValueFromExpression("channels", str(self.channels))
        if index == 3:
            return self.valobj.CreateValueFromExpression("type", f'"{self.type_name}"')
        if index == 4:
            # Create a typed array view of the data
            # We calculate total elements: rows * cols * channels
            count = self.rows * self.cols * self.channels
            if self.data_ptr.IsValid() and self.data_ptr.GetValueAsUnsigned(0) != 0:
                # Cast 'data' (usually uchar*) to the actual type pointer
                target = self.valobj.GetTarget()
                type_obj = target.FindFirstType(self.type_name)
                if type_obj.IsValid():
                     typed_ptr = self.data_ptr.Cast(type_obj.GetPointerType())
                     return typed_ptr
            return self.data_ptr
        return None

def CVMatSummaryProvider(valobj, internal_dict):
    rows = get_member_val(valobj, "rows")
    cols = get_member_val(valobj, "cols")
    flags = get_member_val(valobj, "flags")
    
    depth = flags & 7
    channels = ((flags & 0xfff) >> 3) + 1
    
    type_names = ["UINT8", "INT8", "UINT16", "INT16", "INT32", "FLOAT32", "FLOAT64", "USER"]
    t_name = type_names[depth] if depth < 8 else "USER"
    
    return f"{{{t_name}, {channels} x {cols} x {rows}}}"

# ------------------------------------------------------------------------------
# Geometry (Point, Rect, Size)
# ------------------------------------------------------------------------------
def PointSummary(valobj, internal_dict):
    x = get_member_str(valobj, "x")
    y = get_member_str(valobj, "y")
    return f"{x} {y}"

def Point3Summary(valobj, internal_dict):
    x = get_member_str(valobj, "x")
    y = get_member_str(valobj, "y")
    z = get_member_str(valobj, "z")
    return f"{x} {y} {z}"

def SizeSummary(valobj, internal_dict):
    w = get_member_str(valobj, "width")
    h = get_member_str(valobj, "height")
    return f"{w}x{h}"

def RectSummary(valobj, internal_dict):
    x = get_member_val(valobj, "x")
    y = get_member_val(valobj, "y")
    w = get_member_val(valobj, "width")
    h = get_member_val(valobj, "height")
    return f"{x} {y} {x+w} {y+h} [{w}x{h}]"

def RotatedRectSummary(valobj, internal_dict):
    center = valobj.GetChildMemberWithName("center")
    size = valobj.GetChildMemberWithName("size")
    angle = get_member_str(valobj, "angle")
    
    # We rely on recursively calling summary for center/size if available, 
    # otherwise fallback to simple text
    c_sum = center.GetSummary() if center.IsValid() else "{...}"
    s_sum = size.GetSummary() if size.IsValid() else "{...}"
    
    return f"center={c_sum} size={s_sum} angle={angle} deg"

def RangeSummary(valobj, internal_dict):
    start = get_member_val(valobj, "start")
    end = get_member_val(valobj, "end")
    if start == end:
        return "empty"
    return f"[{start},{end})"

# ------------------------------------------------------------------------------
# Vectors & Matrices (Vec, Scalar, Matx)
# ------------------------------------------------------------------------------
class VecSyntheticProvider:
    def __init__(self, valobj, internal_dict):
        self.valobj = valobj
        self.val = None

    def update(self):
        self.val = self.valobj.GetChildMemberWithName("val")

    def num_children(self):
        if self.val.IsValid():
            return self.val.GetNumChildren()
        return 0

    def get_child_index(self, name):
        try:
            return int(name.strip('[]'))
        except:
            return -1

    def get_child_at_index(self, index):
        return self.val.GetChildAtIndex(index)

class MatxSyntheticProvider:
    # Used for cv::Matx. Similar to Vec but we might want to group rows if we want to match Natvis perfectly.
    # For LLDB, exposing the flat array 'val' is usually sufficient and cleaner.
    def __init__(self, valobj, internal_dict):
        self.valobj = valobj
        self.val = None

    def update(self):
        self.val = self.valobj.GetChildMemberWithName("val")

    def num_children(self):
        if self.val.IsValid():
            return self.val.GetNumChildren()
        return 0

    def get_child_index(self, name):
        try:
            return int(name)
        except:
            return -1

    def get_child_at_index(self, index):
        return self.val.GetChildAtIndex(index)

def MatxSummary(valobj, internal_dict):
    # Get the full type name, e.g., "TMatrix<double, 3, 3>" or "cv::Matx<float, 4, 4>"
    t_name = valobj.GetType().GetName()
    
    import re
    # Regex to find the last two numeric template arguments (rows, cols)
    # This handles complex types like TMatrix<float, 3, 3> genericly
    # It looks for: comma, space(opt), digits, comma, space(opt), digits, closing angle bracket
    match = re.search(r",\s*(\d+),\s*(\d+)\s*>$", t_name)
    if match:
        rows = match.group(1)
        cols = match.group(2)
        return f"[{rows}, {cols}]"
    
    return "Matrix"

# ------------------------------------------------------------------------------
# cv::Ptr (Smart Pointer)
# ------------------------------------------------------------------------------
class PtrSyntheticProvider:
    def __init__(self, valobj, internal_dict):
        self.valobj = valobj
        self.obj = None

    def update(self):
        self.obj = self.valobj.GetChildMemberWithName("obj")

    def num_children(self):
        return 1

    def get_child_index(self, name):
        if name == "ptr": return 0
        return -1

    def get_child_at_index(self, index):
        if index == 0 and self.obj.IsValid():
            # Dereference the pointer to show the actual object
            return self.obj.Dereference()
        return None

def PtrSummary(valobj, internal_dict):
    obj = valobj.GetChildMemberWithName("obj")
    refcount = valobj.GetChildMemberWithName("refcount")
    
    if not obj.IsValid() or obj.GetValueAsUnsigned(0) == 0:
        return "empty"
    
    rc = 0
    if refcount.IsValid():
        rc = refcount.Dereference().GetValueAsUnsigned(0)
        
    return f"Ptr {{...}} [{rc} refs]"

# ------------------------------------------------------------------------------
# cv::AutoBuffer
# ------------------------------------------------------------------------------
def AutoBufferSummary(valobj, internal_dict):
    sz = get_member_val(valobj, "size")
    return f"{{size = {sz}}}"

class AutoBufferSyntheticProvider:
    def __init__(self, valobj, internal_dict):
        self.valobj = valobj
        self.ptr = None
        self.size = 0
        self.item_type = None

    def update(self):
        self.ptr = self.valobj.GetChildMemberWithName("ptr")
        self.size = get_member_val(self.valobj, "size")
        if self.ptr.IsValid():
            self.item_type = self.ptr.GetType().GetPointeeType()

    def num_children(self):
        return self.size

    def get_child_index(self, name):
        try:
            return int(name.strip('[]'))
        except:
            return -1

    def get_child_at_index(self, index):
        if index < 0 or index >= self.size:
            return None
        offset = index * self.item_type.GetByteSize()
        return self.ptr.CreateChildAtOffset(f"[{index}]", offset, self.item_type)

# ------------------------------------------------------------------------------
# cv::Complex
# ------------------------------------------------------------------------------
def ComplexSummary(valobj, internal_dict):
    re = valobj.GetChildMemberWithName("re")
    im = valobj.GetChildMemberWithName("im")
    
    r_val = re.GetValueAsSigned(0) if "int" in re.GetType().GetName() else float(re.GetValue())
    i_val = im.GetValueAsSigned(0) if "int" in im.GetType().GetName() else float(im.GetValue())
    
    if i_val == 0:
        return f"{r_val}"
    if r_val == 0:
        return f"i*{i_val}"
    
    sign = "+" if i_val >= 0 else ""
    return f"{r_val}{sign}i*{i_val}"
