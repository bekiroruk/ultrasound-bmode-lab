cmake_minimum_required(VERSION 3.18)
project(ultrasound_native LANGUAGES CXX)

add_library(ultrasound_native SHARED beamformer.cpp)
target_compile_features(ultrasound_native PRIVATE cxx_std_17)

find_package(OpenMP)
if(OpenMP_CXX_FOUND)
  target_link_libraries(ultrasound_native PRIVATE OpenMP::OpenMP_CXX)
endif()

if(MSVC)
  target_compile_options(ultrasound_native PRIVATE /O2)
else()
  target_compile_options(ultrasound_native PRIVATE -O3 -ffast-math)
endif()
