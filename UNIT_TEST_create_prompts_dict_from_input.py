
from server import create_key_prompt_list_from_input
from server import create_prompts_list_from_dict


data = [
    {
        'text_segments': ['Hi'], 
        'variable_names': [], 
        'variable_values': []},
    {
        'text_segments': ['Write a concise description of unique charachteristics of ', ' trees.\n\n'], 
        'variable_names': ['tree type'], 
        'variable_values': [['Oak', 'Spruse']]
    },
    {
        "text_segments": [
            "Write me a ",
            " description about the animal ",
            ". Use ",
            " language.",
        ],
        "variable_names": ["length", "animal", "formality"],
        "variable_values": [
            ["short", "medium", "long"],
            ["tiger", "elephant", "rino"],
            ["formal", "casual"],
        ],
    },
    {
        "text_segments": ["", " is a term to describe what?"],
        "variable_names": ["term"],
        "variable_values": [["short", "medium", "long"]],
    },
    {
        'text_segments': ['What are ', ''], 
        'variable_names': ['object'], 
        'variable_values': [['doors', 'cars']]}
]


dicts = []
for d in data:
    dict = create_key_prompt_list_from_input(d['text_segments'],d['variable_values'])
    print(dict)
    dicts.append(dict)

print('\n\n\n\n')

#lists = []
#for dict in dicts:
#    list = create_prompts_list_from_dict(dict)
#    print(list)
#    lists.append(list)