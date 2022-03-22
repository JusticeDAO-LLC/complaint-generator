class UserPresentableException(Exception):
    def __init__(self, id, description):
        super().__init__(id)
        self.description = description