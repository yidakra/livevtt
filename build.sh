#!/bin/bash
# Convenience build script for LiveVTT Caption Module
# This script calls the actual build script in the proper location

echo "🔨 Building LiveVTT Caption Module..."
echo "===================================="

cd deploy/scripts && ./java_module_build.sh
