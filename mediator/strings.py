user_prompts = {
    'genesis_question': 'Please give a quick summary of your complaint.'
}

model_prompts = {
    'generate_questions': '"""\n{complaint}\n"""\n\nGenerate a list of questions that an attorney would ask their client about this legal lawsuit.',
    'summarize_complaint': '"""\n{inquiries}\n"""\n\nGenerate a very long detailed summary about the Plaintiff\'s legal complaint from this conversation.',
    'inquiry_block': 'Lawyer: {lawyer}\nPlaintiff: {plaintiff}'
}