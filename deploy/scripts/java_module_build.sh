#!/bin/bash
# Script to compile and package the LiveVTT caption module for Wowza Streaming Engine
# Version 1.1.0 - January 2025
# Includes fixes for HTTP provider 404 issues and enhanced logging

# Configuration
WOWZA_LIB_DIR="/usr/local/WowzaStreamingEngine/lib/"
MODULE_NAME="livevtt-caption-module"
PACKAGE_NAME="com.livevtt.wowza"
BUILD_DIR="../../build"
CLASSES_DIR="$BUILD_DIR/classes"
SRC_DIR="../../src/java"
JAR_FILE="$BUILD_DIR/$MODULE_NAME.jar"

echo "========================================"
echo "LiveVTT Caption Module Build Script v1.1.0"
echo "========================================"

# Check if Wowza is installed
if [ ! -d "$WOWZA_LIB_DIR" ]; then
    echo "Error: Wowza Streaming Engine libraries not found at $WOWZA_LIB_DIR"
    echo "Please install Wowza Streaming Engine or update the WOWZA_LIB_DIR variable."
    exit 1
fi

# Create build directories
mkdir -p "$CLASSES_DIR"
mkdir -p "$BUILD_DIR"

# Find Wowza libraries
WOWZA_JARS=$(find "$WOWZA_LIB_DIR" -name "*.jar" | tr '\n' ':')
if [ -z "$WOWZA_JARS" ]; then
    echo "Error: No JAR files found in $WOWZA_LIB_DIR"
    exit 1
fi

# Compile Java files
echo "Compiling Java files..."
echo "- LiveVTTCaptionModule.java (Caption processing module)"
echo "- LiveVTTCaptionHTTPProvider.java (HTTP provider with 404 fix)"
javac -cp "$WOWZA_JARS" -d "$CLASSES_DIR" "$SRC_DIR/LiveVTTCaptionModule.java" "$SRC_DIR/LiveVTTCaptionHTTPProvider.java"

if [ $? -ne 0 ]; then
    echo "Error: Compilation failed"
    exit 1
fi

# Create package directory structure
mkdir -p "$CLASSES_DIR/com/livevtt/wowza"

# Move class files to package directory
mv "$CLASSES_DIR"/*.class "$CLASSES_DIR/com/livevtt/wowza/"

# Create JAR file
echo "Creating JAR file: $JAR_FILE"
jar cvf "$JAR_FILE" -C "$CLASSES_DIR" .

if [ $? -ne 0 ]; then
    echo "Error: Failed to create JAR file"
    exit 1
fi

echo ""
echo "✅ Build successful: $JAR_FILE"
echo "✅ Module version: 1.1.0 (includes HTTP provider 404 fix)"
echo ""
echo "🔧 INSTALLATION INSTRUCTIONS:"
echo "========================================"
echo ""
echo "1. Copy the JAR file to Wowza lib directory:"
echo "   cp $JAR_FILE $WOWZA_LIB_DIR/"
echo ""
echo "2. Configure the module in Application.xml:"
echo "   <Module>"
echo "       <n>LiveVTTCaptionModule</n>"
echo "       <Description>LiveVTT Caption Module for real-time closed captioning</Description>"
echo "       <Class>com.livevtt.wowza.LiveVTTCaptionModule</Class>"
echo "   </Module>"
echo ""
echo "3. Configure the HTTP provider in VHost.xml:"
echo "   (Ensure this is under the HostPort that LiveVTT will send captions to, typically port 8086)"
echo "   <HTTPProvider>"
echo "       <BaseClass>com.livevtt.wowza.LiveVTTCaptionHTTPProvider</BaseClass>"
echo "       <RequestFilters>livevtt/captions*</RequestFilters>"
echo "       <AuthenticationMethod>none</AuthenticationMethod>"
echo "   </HTTPProvider>"
echo ""
echo "4. Add debug logging (recommended for testing):"
echo "   <Property>"
echo "       <n>livevtt.caption.debug</n>"
echo "       <Value>true</Value>"
echo "       <Type>Boolean</Type>"
echo "   </Property>"
echo ""
echo "5. Restart Wowza Streaming Engine"
echo ""
echo "🧪 TESTING:"
echo "========================================"
echo ""
echo "Test HTTP provider status:"
echo "   curl \"http://localhost:8086/livevtt/captions/status\""
echo ""
echo "Test caption submission:"
echo "   curl -X POST \"http://localhost:8086/livevtt/captions\" \\"
echo "        -H \"Content-Type: application/json\" \\"
echo "        -d '{\"text\":\"Test caption\",\"lang\":\"eng\",\"trackid\":99,\"streamname\":\"myStream\"}'"
echo ""
echo "📚 For detailed setup instructions, see WOWZA_SETUP.md"
echo "🐛 For troubleshooting, see the troubleshooting section in WOWZA_SETUP.md" 
