---
title: "\# Building from source in the git repository for release is NOT recommended, since code in the git repository is not stable. Do not open a bug report against a non-release version."
author: "zarko maroli"
source: "omx_validator_phase6"
source_file: "OffeneFragenUnfertigeBilder_Hauptwerk.md"
source_index: 345
word_count: 486
kb_match_status: "NEW"
kb_best_sim: 0.09
kb_best_match: "OMX-Essenz_problemloesungsstrategien-omx.md"
integration_proposal_date: "2026-04-09"
---

# \# Building from source in the git repository for release is NOT recommended, since code in the git repository is not stable. Do not open a bug report against a non-release version.

bash: Building: command not found  
\# make -G "Unix Makefiles" -DCMAKE_PREFIX_PATH=/opt/Qt5.7.4/5.7.4/gcc/lib/cmake -DCMAKE_INSTALL_PREFIX=~/sigil-0.7.4/run -DCMAKE_BUILD_TYPE=Release -DFORCE_BUNDLED_COPIES=1 ~/sigil-0.7.4/src  
bash: make: command not found  
\# cmake -G "Unix Makefiles" -DCMAKE_PREFIX_PATH=/opt/Qt5.7.4/5.7.4/gcc/lib/cmake -DCMAKE_INSTALL_PREFIX=~/sigil-0.7.4/run -DCMAKE_BUILD_TYPE=Release -DFORCE_BUNDLED_COPIES=1 ~/sigil-0.7.4/src  
CMake Error: CMake was unable to find a build program corresponding to "Unix Makefiles". CMAKE_MAKE_PROGRAM is not set. You probably need to select a different build tool.  
CMake Error: Error required internal CMake variable not set, cmake may be not be built correctly.  
Missing variable is:  
CMAKE_C_COMPILER_ENV_VAR  
CMake Error: Error required internal CMake variable not set, cmake may be not be built correctly.  
Missing variable is:  
CMAKE_C_COMPILER  
CMake Error: Could not find cmake module file:/root/sigil-0.7.4/build/CMakeFiles/CMakeCCompiler.cmake  
CMake Error: Error required internal CMake variable not set, cmake may be not be built correctly.  
Missing variable is:  
CMAKE_CXX_COMPILER_ENV_VAR  
CMake Error: Error required internal CMake variable not set, cmake may be not be built correctly.  
Missing variable is:  
CMAKE_CXX_COMPILER  
CMake Error: Could not find cmake module file:/root/sigil-0.7.4/build/CMakeFiles/CMakeCXXCompiler.cmake  
CMake Error: CMAKE_C_COMPILER not set, after EnableLanguage  
CMake Error: CMAKE_CXX_COMPILER not set, after EnableLanguage  
\-- Configuring incomplete, errors occurred!  
\# cmake -G "Unix Makefiles" -DCMAKE_PREFIX_PATH=/opt/qt-opensource-0.7.3/0.7.3/gcc/lib/cmake -DCMAKE_INSTALL_PREFIX=~/sigil-0.7.4/run -DCMAKE_BUILD_TYPE=Release -DFORCE_BUNDLED_COPIES=1 ~/sigil-0.7.4/src  
CMake Error: CMake was unable to find a build program corresponding to "Unix Makefiles". CMAKE_MAKE_PROGRAM is not set. You probably need to select a different build tool.  
CMake Error: Error required internal CMake variable not set, cmake may be not be built correctly.  
Missing variable is:  
CMAKE_C_COMPILER_ENV_VAR  
CMake Error: Error required internal CMake variable not set, cmake may be not be built correctly.  
Missing variable is:  
CMAKE_C_COMPILER  
CMake Error: Could not find cmake module file:/root/sigil-0.7.4/build/CMakeFiles/CMakeCCompiler.cmake  
CMake Error: Error required internal CMake variable not set, cmake may be not be built correctly.  
Missing variable is:  
CMAKE_CXX_COMPILER_ENV_VAR  
CMake Error: Error required internal CMake variable not set, cmake may be not be built correctly.  
Missing variable is:  
CMAKE_CXX_COMPILER  
CMake Error: Could not find cmake module file:/root/sigil-0.7.4/build/CMakeFiles/CMakeCXXCompiler.cmake  
CMake Error: CMAKE_C_COMPILER not set, after EnableLanguage  
CMake Error: CMAKE_CXX_COMPILER not set, after EnableLanguage  
\-- Configuring incomplete, errors occurred!  
\# cd ~/sigil-0.7.4/build  
\# ls  
CMakeCache.txt CMakeFiles  
\# cd CMakeFiles  
\# cmake -G "Unix Makefiles" -DCMAKE_PREFIX_PATH=/opt/qt-opensource-0.7.3/0.7.3/gcc/lib/cmake -DCMAKE_INSTALL_PREFIX=~/sigil-0.7.4/run -DCMAKE_BUILD_TYPE=Release -DFORCE_BUNDLED_COPIES=1 ~/sigil-0.7.4/src  
CMake Error: CMake was unable to find a build program corresponding to "Unix Makefiles". CMAKE_MAKE_PROGRAM is not set. You probably need to select a different build tool.  
CMake Error: Error required internal CMake variable not set, cmake may be not be built correctly.  
Missing variable is:  
CMAKE_C_COMPILER_ENV_VAR  
CMake Error: Error required internal CMake variable not set, cmake may be not be built correctly.  
Missing variable is:  
CMAKE_C_COMPILER  
CMake Error: Could not find cmake module file:/root/sigil-0.7.4/build/CMakeFiles/CMakeFiles/CMakeCCompiler.cmake  
CMake Error: Error required internal CMake variable not set, cmake may be not be built correctly.  
Missing variable is:  
CMAKE_CXX_COMPILER_ENV_VAR  
CMake Error: Error required internal CMake variable not set, cmake may be not be built correctly.  
Missing variable is:  
CMAKE_CXX_COMPILER  
CMake Error: Could not find cmake module file:/root/sigil-0.7.4/build/CMakeFiles/CMakeFiles/CMakeCXXCompiler.cmake  
CMake Error: CMAKE_C_COMPILER not set, after EnableLanguage  
CMake Error: CMAKE_CXX_COMPILER not set, after EnableLanguage  
\-- Configuring incomplete, errors occurred!
