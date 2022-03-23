# The Mediator

Core logic of the complaint generator. Sits between the frontend application and the deep learning model.

## Overview

![Complaint Generator Mediator](https://user-images.githubusercontent.com/13929820/159747598-01bea9f8-2087-4ee2-869b-aede394cb168.svg)

The Mediator module is the external facing interface and has the function signatures as shown in the diagram. These are the only methods callable by the application modules, such as the CLI app.
Arrow directions indicate dependencies.
