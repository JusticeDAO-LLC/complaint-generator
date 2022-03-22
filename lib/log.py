import logging

def init_logging(level):
    logging.basicConfig(
        format='%(asctime)s %(levelname).1s [\x1b[33;20m%(name)s\x1b[0m] %(message)s', 
        datefmt='%d-%b-%y %H:%M:%S',
        level=level
    )

def make_logger(name):
    return logging.getLogger(name)