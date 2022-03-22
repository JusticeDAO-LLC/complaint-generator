from lib.log import make_logger

log = make_logger('cli')


class CLI:
    def __init__(self, mediator):
        self.mediator = mediator

        log.info('created CLI app')

        print('')
        print('*** JusticeDAO / Complaint Generator v1.0 ***')
        print('')
        print('commands are:')
        self.print_commands()

        self.loop()


    def loop(self):
        while True:
            text = input('> ')
            print('')

            if text[0] == '!':
                self.interpret_command(text[1:])
            else:
                self.feed(text)
            
    def feed(self, text):
        pass


    def interpret_command(self, line):
        parts = line.split(' ')
        command = parts[0]

        if command == 'new':
            self.mediator.reset()
        else:
            print('command unknown, available commands are:')
            self.print_commands()


    def print_commands(self):
        print('!new       starts a new complaint flow')
        print('!resume    resumes from a statefile from disk')
        print('!save      saves current state to disk')
        print('')