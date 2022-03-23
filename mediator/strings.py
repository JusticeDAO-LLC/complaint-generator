user_prompts = {
    'genesis_question': 'Please give a quick summary of your complaint.'
}

model_prompts = {
    'generate_questions': 'Generate a list of questions that an attorney would ask their client about this legal lawsuit.\n\n"""\n{complaint}\n"""',
    'summarize_complaint': 'Generate a very long detailed summary about the Plaintiff\'s legal complaint from this conversation:\n\n"""\n{inquiries}\n"""',
    'inquiry_block': 'Lawyer: {lawyer}\nPlaintiff: {plaintiff}'
}