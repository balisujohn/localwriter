#!/bin/bash
# Build script for the LocalWriter .oxt extension package

# Extension name
EXTENSION_NAME="localwriter"

# Remove old package if it exists
if [ -f "${EXTENSION_NAME}.oxt" ]; then
    echo "Removing old package..."
    rm "${EXTENSION_NAME}.oxt"
fi

# Build UNO type library from IDL if idl/ directory exists
if [ -d "idl" ] && [ -f "idl/XPromptFunction.idl" ]; then
    echo "Building XPromptFunction.rdb from IDL..."
    TYPES_RDB=$(find /usr/lib/libreoffice /usr/share/libreoffice -name "types.rdb" 2>/dev/null | head -1)
    OFFAPI_RDB=$(find /usr/lib/libreoffice /usr/share/libreoffice -path "*/types/offapi.rdb" 2>/dev/null | head -1)
    UNOIDL_WRITE=$(which unoidl-write 2>/dev/null || find /usr/lib/libreoffice /usr/share/libreoffice -name "unoidl-write" 2>/dev/null | head -1)

    if [ -n "$UNOIDL_WRITE" ] && [ -n "$TYPES_RDB" ] && [ -n "$OFFAPI_RDB" ]; then
        "$UNOIDL_WRITE" "$TYPES_RDB" "$OFFAPI_RDB" idl/XPromptFunction.idl XPromptFunction.rdb
        echo "XPromptFunction.rdb built successfully"
    else
        echo "Warning: unoidl-write or LibreOffice type libraries not found, skipping RDB build"
        echo "  Install libreoffice-dev to enable: sudo apt install libreoffice-dev"
    fi
fi

# Create the new package
echo "Creating package ${EXTENSION_NAME}.oxt..."
zip -r "${EXTENSION_NAME}.oxt" \
    Accelerators.xcu \
    Addons.xcu \
    CalcAddIn.xcu \
    XPromptFunction.rdb \
    assets \
    description.xml \
    main.py \
    prompt_function.py \
    pythonpath \
    META-INF \
    registration \
    README.md

if [ $? -eq 0 ]; then
    echo "Package created successfully: ${EXTENSION_NAME}.oxt"
    echo ""
    echo "To install:"
    echo "  1. Open LibreOffice"
    echo "  2. Tools > Extension Manager"
    echo "  3. Add > Select ${EXTENSION_NAME}.oxt"
    echo ""
    echo "Or via command line:"
    echo "  unopkg add ${EXTENSION_NAME}.oxt"
else
    echo "Error creating package"
    exit 1
fi
