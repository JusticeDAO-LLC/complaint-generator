from .strings import *
from .state import *


class Mediator:
    def __init__(self, backends):
        self.backends = backends

    def new(self):
        self.state = State()

    def resume(self, state):
        self.state = state


    def query_backend(self, template, args):
        return self.backends[0].prompt(model_prompts[template].format(**args))

    