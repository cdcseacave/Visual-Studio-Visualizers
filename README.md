# Custom Visualizers for Visual Studio and LLDB Debuggers

This repository provides a collection of custom debugger visualizers for commonly used libraries such as **Eigen** and **OpenCV**, as well as for custom types used within **OpenMVS**.

Visualizers for **Visual Studio IDE** are implemented using the **Natvis** framework, enabling clearer and more intuitive representation of native data types in the debugger’s variable inspection windows.

For **LLDB**, the `LLDB` directory contains Python-based formatter scripts that offer equivalent custom visualizations when debugging on platforms that use LLDB, including **Visual Studio Code IDE**.

These visualizers aim to improve debugging efficiency by presenting complex data structures in a readable and structured format across both debugging environments.
