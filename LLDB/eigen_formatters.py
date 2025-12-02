import lldb
import re

def __lldb_init_module(debugger, internal_dict):
    # Register formatters for Eigen::Matrix and Eigen::Array
    # Regex covers: Eigen::Matrix<...>, Eigen::Array<...>, Eigen::Vector3d, etc.
    # Note: Typedefs like Vector3d usually resolve to Eigen::Matrix<double, 3, 1, ...> in LLDB.
    debugger.HandleCommand('type synthetic add -x "^Eigen::Matrix<.+>$" --python-class eigen_formatters.EigenMatrixSyntheticProvider')
    debugger.HandleCommand('type summary add -x "^Eigen::Matrix<.+>$" --python-function eigen_formatters.EigenMatrixSummaryProvider')
    
    debugger.HandleCommand('type synthetic add -x "^Eigen::Array<.+>$" --python-class eigen_formatters.EigenMatrixSyntheticProvider')
    debugger.HandleCommand('type summary add -x "^Eigen::Array<.+>$" --python-function eigen_formatters.EigenMatrixSummaryProvider')

    # Eigen::Map
    debugger.HandleCommand('type synthetic add -x "^Eigen::Map<.+>$" --python-class eigen_formatters.EigenMatrixSyntheticProvider')
    debugger.HandleCommand('type summary add -x "^Eigen::Map<.+>$" --python-function eigen_formatters.EigenMatrixSummaryProvider')

    # Eigen::Quaternion
    debugger.HandleCommand('type summary add -x "^Eigen::Quaternion<.+>$" --python-function eigen_formatters.EigenQuaternionSummaryProvider')
    debugger.HandleCommand('type synthetic add -x "^Eigen::Quaternion<.+>$" --python-class eigen_formatters.EigenQuaternionSyntheticProvider')

    # Eigen::SparseMatrix
    debugger.HandleCommand('type summary add -x "^Eigen::SparseMatrix<.+>$" --python-function eigen_formatters.EigenSparseMatrixSummaryProvider')

# ------------------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------------------
def get_child_val(valobj, *names):
    """Helper to try multiple member names (handles different Eigen versions)."""
    for name in names:
        child = valobj.GetChildMemberWithName(name)
        if child.IsValid():
            return child
        # Try path lookup for nested members like m_storage.m_data
        if "." in name:
            child = valobj.GetValueForExpressionPath(f".{name}")
            if child.IsValid():
                return child
    return None

def get_child_value_int(valobj, *names):
    child = get_child_val(valobj, *names)
    if child and child.IsValid():
        # Check for wrapper structs like 'm_value' (Eigen::internal::variable_if_dynamic)
        if child.GetChildMemberWithName("m_value").IsValid():
            return child.GetChildMemberWithName("m_value").GetValueAsUnsigned()
        return child.GetValueAsUnsigned()
    return None

# ------------------------------------------------------------------------------
# Eigen::Matrix / Array / Map
# ------------------------------------------------------------------------------
class EigenMatrixSyntheticProvider:
    def __init__(self, valobj, internal_dict):
        self.valobj = valobj
        self.rows = 0
        self.cols = 0
        self.size = 0
        self.data_ptr = None
        self.scalar_type = None
        self.element_size = 0
        self.is_row_major = False

    def update(self):
        try:
            # --- 1. Dimensions Parsing (Keep existing logic) ---
            type_name = self.valobj.GetType().GetCanonicalType().GetName()
            short_name = re.sub(r"^Eigen::(Matrix|Array|Map)<", "", type_name)
            args = [x.strip() for x in short_name.rsplit('>', 1)[0].split(',')]

            R_template = -1
            C_template = -1
            Options = 0 # Default ColMajor

            # Attempt to parse template args
            if len(args) >= 2:
                idx_start = 1
                for i, arg in enumerate(args):
                    if re.match(r"^-?\d+$", arg) or "Dynamic" in arg:
                        idx_start = i
                        break
                try:
                    R_template = -1 if "Dynamic" in args[idx_start] else int(args[idx_start])
                    C_template = -1 if "Dynamic" in args[idx_start+1] else int(args[idx_start+1])
                    if len(args) > idx_start + 2:
                        Options = int(args[idx_start+2])
                except:
                    pass

            self.rows = R_template
            self.cols = C_template
            
            # Read runtime dimensions if dynamic
            if self.rows == -1:
                self.rows = get_child_value_int(self.valobj, "m_rows", "m_storage.m_rows") or 0
            if self.cols == -1:
                self.cols = get_child_value_int(self.valobj, "m_cols", "m_storage.m_cols") or 0
            
            self.size = self.rows * self.cols
            self.is_row_major = (Options & 1) == 1

            # --- 2. Data Pointer Detection (THE FIX) ---
            
            # Strategy A: Try standard path (m_data)
            self.data_ptr = get_child_val(self.valobj, "m_data", "m_storage.m_data")

            # Strategy B: Fixed size matrices often store data in a struct named 'm_data' 
            # which contains a member 'array'. We need the address of that array.
            if self.data_ptr.IsValid():
                # Check if this is the "compressed" storage struct
                array_member = self.data_ptr.GetChildMemberWithName("array")
                if array_member.IsValid():
                    self.data_ptr = array_member

                # If we have an array (e.g. double[9]), we need to decay it to a pointer
                # so CreateChildAtOffset works correctly.
                if self.data_ptr.GetType().IsArrayType():
                    self.data_ptr = self.data_ptr.GetChildAtIndex(0)
                    # GetChildAtIndex(0) returns the first element. 
                    # We want the address of the first element to act as our base pointer.
                    self.data_ptr = self.data_ptr.AddressOf()

            # Strategy C: If logic above failed, fallback to the address of the matrix object itself.
            # (Fixed size Eigen matrices usually start memory at offset 0 of the object)
            if (not self.data_ptr.IsValid() or self.data_ptr.GetValueAsUnsigned() == 0) and self.size > 0:
                if R_template != -1 and C_template != -1:
                    # It is fixed size, assume data starts at 'this'
                    self.data_ptr = self.valobj.AddressOf()
                    # Cast 'this' to scalar pointer
                    scalar_type_name = args[0] # Roughly the first template arg
                    target = self.valobj.GetTarget()
                    
                    # Try to find the type from the string name
                    # If that fails, guess based on common types
                    type_obj = target.FindFirstType(scalar_type_name)
                    if not type_obj.IsValid():
                        # Fallback for aliases like 'Vector3d' -> 'double'
                        if "double" in type_name: type_obj = target.FindFirstType("double")
                        elif "float" in type_name: type_obj = target.FindFirstType("float")
                    
                    if type_obj.IsValid():
                        self.data_ptr = self.data_ptr.Cast(type_obj.GetPointerType())

            # --- 3. Final Type Setup ---
            if self.data_ptr.IsValid():
                self.scalar_type = self.data_ptr.GetType().GetPointeeType()
                self.element_size = self.scalar_type.GetByteSize()

        except Exception as e:
            pass

    def num_children(self):
        return self.size

    def get_child_index(self, name):
        try:
            # Support [i] for vectors and [r,c] for matrices
            if "," in name:
                r, c = map(int, name.strip("[]").split(","))
                if self.is_row_major:
                    return r * self.cols + c
                else:
                    return c * self.rows + r
            else:
                return int(name.strip("[]"))
        except:
            return -1

    def get_child_at_index(self, index):
        if index < 0 or index >= self.size:
            return None
        
        # Calculate row/col for naming
        if self.is_row_major:
            r = index // self.cols
            c = index % self.cols
        else:
            c = index // self.rows
            r = index % self.rows
            
        offset = index * self.element_size
        
        # Name: [i] if vector, [r, c] if matrix
        if self.rows == 1 or self.cols == 1:
            name = f"[{index}]"
        else:
            name = f"[{r}, {c}]"

        return self.data_ptr.CreateChildAtOffset(name, offset, self.scalar_type)

def EigenMatrixSummaryProvider(valobj, internal_dict):
    # Reuse synthetic provider logic to get dimensions
    synth = EigenMatrixSyntheticProvider(valobj, internal_dict)
    synth.update()
    
    # Identify specific types
    t_name = valobj.GetType().GetName()
    
    layout = "RowMajor" if synth.is_row_major else "ColMajor"
    shape = f"{synth.rows} x {synth.cols}"
    
    if "Array" in t_name:
        return f"Array [{shape}] {layout}"
    if "Map" in t_name:
        return f"Map [{shape}] {layout}"
        
    return f"Matrix [{shape}] {layout}"

# ------------------------------------------------------------------------------
# Eigen::Quaternion
# ------------------------------------------------------------------------------
class EigenQuaternionSyntheticProvider:
    def __init__(self, valobj, internal_dict):
        self.valobj = valobj
        self.coeffs = None

    def update(self):
        self.coeffs = self.valobj.GetChildMemberWithName("m_coeffs")

    def num_children(self):
        return 4 if self.coeffs.IsValid() else 0

    def get_child_index(self, name):
        if name == "x": return 0
        if name == "y": return 1
        if name == "z": return 2
        if name == "w": return 3
        return -1

    def get_child_at_index(self, index):
        if not self.coeffs.IsValid(): return None
        
        # m_coeffs is usually an Eigen::Matrix<T, 4, 1>
        # We need to access its data. Using the SyntheticProvider for Matrix recursively 
        # is hard, so we just dig for data manually.
        
        # Try to find data ptr of coeffs
        data_ptr = get_child_val(self.coeffs, "m_data", "m_storage.m_data")
        
        # Unwrap array if needed (fixed size)
        if data_ptr.IsValid():
             array_member = data_ptr.GetChildMemberWithName("array")
             if array_member.IsValid():
                 data_ptr = array_member
             if data_ptr.GetType().IsArrayType():
                 data_ptr = data_ptr.GetChildAtIndex(0).GetAddress()
        
        if not data_ptr.IsValid(): return None

        type_obj = data_ptr.GetType().GetPointeeType()
        size = type_obj.GetByteSize()
        offset = index * size
        
        names = ["x", "y", "z", "w"]
        return data_ptr.CreateChildAtOffset(names[index], offset, type_obj)

def EigenQuaternionSummaryProvider(valobj, internal_dict):
    synth = EigenQuaternionSyntheticProvider(valobj, internal_dict)
    synth.update()
    
    try:
        x = synth.get_child_at_index(0).GetValue()
        y = synth.get_child_at_index(1).GetValue()
        z = synth.get_child_at_index(2).GetValue()
        w = synth.get_child_at_index(3).GetValue()
        return f"(x={x}, y={y}, z={z}, w={w})"
    except:
        return "Quaternion"

# ------------------------------------------------------------------------------
# Eigen::SparseMatrix
# ------------------------------------------------------------------------------
def EigenSparseMatrixSummaryProvider(valobj, internal_dict):
    rows = get_child_value_int(valobj, "m_rows", "m_storage.m_rows")
    cols = get_child_value_int(valobj, "m_cols", "m_storage.m_cols")
    
    # Non-zeros usually in m_data.size() or similar, but structure varies.
    # Compressed storage usually has `m_data` (Values), `m_innerIndices`, `m_outerIndexPtr`.
    # A safe summary is just dimensions.
    
    if rows is None or cols is None:
        return "SparseMatrix"
        
    return f"SparseMatrix [{rows} x {cols}]"
