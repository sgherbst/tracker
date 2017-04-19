# tracker

## Introduction

Program to track flies with an overhead camera mounted on a CNC rig.  TVs surrounding the fly provide visual stimuli that react to the fly's position.

## Instructions

These instructions assume a Windows build platform.

```
> git clone https://github.com/ClandininLab/tracker.git
> cd tracker
> mkdir build
> cd build
> cmake .. -G "Visual Studio 12 Win64" -DCMAKE_BUILD_TYPE=Release
> cmake --build . --target ALL_BUILD --config Release
> cd Release
> tracker
```
