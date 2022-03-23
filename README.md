# Complaint Generator
### by JusticeDAO



## Overview

![Complaint Generator Overview](https://user-images.githubusercontent.com/13929820/159738867-25593733-fc54-4683-abc7-a0703ce7d4a7.svg)

Visit the respective directories in this repo for a in-depth view.


## Configuration

The generator's behaviour is entirely defined by the accompanying `.toml` config file. It is defined by the following stanzas:

- `[[BACKENDS]]` defines the kind, access point and credentials for a backend adapter; can be many
- `[MEDIATOR]` defines the configuration for the core logic, like which of the previously defined backends to use; can be only one
- `[APPLICATION]` defines the frontend application to run; can be only one

## Run it yourself

Clone or download this repo into a designated directory. Then run
```
py run.py
```
