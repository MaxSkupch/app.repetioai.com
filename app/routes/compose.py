"""
All Pages and functions related to the compose Pages


ValKey format:
User Specific:      user({id}):{category}:{subcategory}... -> value
Global:             global:{category}:{subcategory}... -> value 

vk.set('global:limits:openai:tpm', 0)
vk.set('global:limits:openai:rpm', 0)
vk.set('global:limits:openai:reset_time', datetime.now().timestamp())



vk.incrby(f'global:user({current_user.id}):request_counts:tokens_used_total',      response.usage.total_tokens)
vk.incrby(f'global:user({current_user.id}):request_counts:tokens_used_prompts',    response.usage.prompt_tokens)
vk.incrby(f'global:user({current_user.id}):request_counts:tokens_used_response',   response.usage.completion_tokens)
vk.incrby(f'global:user({current_user.id}):request_counts:prompts_completed',      1)



response_data = {"response": "API response here"}  # Example API response
redis_client.hset(f"responses:{session_id}", index, json.dumps(response_data))


Get Data---

# Retrieve all responses for the session
responses = redis_client.hgetall(f"responses:{session_id}")

# Sort responses by index (keys)
sorted_responses = sorted(responses.items(), key=lambda x: int(x[0]))

# Convert from Redis format (bytes) to usable Python objects
ordered_responses = [json.loads(value.decode()) for _, value in sorted_responses]
"""


import asyncio
import csv
import json
import os
import re
import tempfile
import tiktoken
import time
import ulid

from datetime       import datetime
from flask          import render_template, abort, request, redirect, url_for, Response, stream_with_context, current_app, send_file, session
from flask_login    import login_required, current_user
from itertools      import product
from zoneinfo       import ZoneInfo

from app            import db
from app.extensions import openai_client
from app.functions  import token_count_to_string
from app.models     import UserSubscription, Request
from app.values     import openai_model_name, openai_model_limit_rpm, openai_model_limit_tpm



#session['compose_data'] = {
#                    'text_segments':    text_segments,
#                    'variable_names':   variable_names,
#                    'variable_values':  [], # list of lists of variable-values
#                }

"""
Setting up the Redis / Valkey interactions

Always one save- and one retrive & delete function per data item
"""

# Composition data

def set_text_segemnts(text_segments: list):
    current_app.vk.set(f"user({current_user.id}):current_composition:input:text_segemnts", text_segments)

def get_del_text_segments():
    result = current_app.vk.get(f"user({current_user.id}):current_composition:input:text_segments")
    current_app.vk.delete(f"user({current_user.id}):current_composition:input:text_segments")
    return result


def set_variable_names(variable_names: list):
    current_app.vk.set(f"user({current_user.id}):current_composition:input:variable_name", variable_names)

def get_del_variable_names():
    result = current_app.vk.get(f"user({current_user.id}):current_composition:input:variable_name")
    current_app.vk.delete(f"user({current_user.id}):current_composition:input:variabl_name")
    return result

def get_nth_variable_name(n):
    return current_app.vk.get(f"user({current_user.id}):current_composition:input:variable_name")[n]
   


def set_variable(vavariable_name: str, vavariable_values: list):
    current_app.vk.hset(f"user({current_user.id}):current_composition:input:variables", vavariable_name, json.dumps(vavariable_values))

def get_del_variables():
    result = current_app.vk.hgetall(f"user({current_user.id}):current_composition:input:variables")
    result = {key: json.loads(value) for key, value in result.items()}
    current_app.vk.delete(f"user({current_user.id}):current_composition:input:variables")
    return result



def set_prompt(prompts: list):  # Should be an ordered list
    for i, prompt in enumerate(prompts):
        current_app.vk.hset(f"user({current_user.id}):current_composition:prompts", i, prompt)

def get_del_prompts():
    result = current_app.vk.hgetall(f"user({current_user.id}):current_composition:prompts")
    current_app.vk.delete(f"user({current_user.id}):current_composition:prompts")
    return result


def set_response(index: int, response: str):
    current_app.vk.hset(f"user({current_user.id}):current_composition:responses", index, response)

def get_del_responses():
    result = current_app.vk.hgetall(f"user({current_user.id}):current_composition:responses")
    current_app.vk.delete(f"user({current_user.id}):current_composition:responses")
    return result



# Composition Meta Data

def init_comp_meta_data(prompts_amount):
    current_app.vk.hset(f"user({current_user.id}):current_composition:meta_data", "tokens_used_total",      0)
    current_app.vk.hset(f"user({current_user.id}):current_composition:meta_data", "tokens_used_prompts",    0)
    current_app.vk.hset(f"user({current_user.id}):current_composition:meta_data", "tokens_used_response",   0)
    current_app.vk.hset(f"user({current_user.id}):current_composition:meta_data", "prompts_completed",      0)
    current_app.vk.hset(f"user({current_user.id}):current_composition:meta_data", "prompts_amount",         prompts_amount)
    current_app.vk.hset(f"user({current_user.id}):current_composition:meta_data", "start_progress_stream",  1)

def incr_comp_meta_data(tokens_used_total: int, tokens_used_prompts: int, tokens_used_response):
    current_app.vk.hincrby(f"user({current_user.id}):current_composition:meta_data", "tokens_used_total",       tokens_used_total)
    current_app.vk.hincrby(f"user({current_user.id}):current_composition:meta_data", "tokens_used_prompts",     tokens_used_prompts)
    current_app.vk.hincrby(f"user({current_user.id}):current_composition:meta_data", "tokens_used_response",    tokens_used_response)
    current_app.vk.hincrby(f"user({current_user.id}):current_composition:meta_data", "prompts_completed",       1)

def get_comp_meta_data():
    tokens_used_total       = current_app.vk.hget(f"user({current_user.id}):current_composition:meta_data", "tokens_used_total", 0)
    tokens_used_prompts     = current_app.vk.hget(f"user({current_user.id}):current_composition:meta_data", "tokens_used_prompts", 0)
    tokens_used_responses   = current_app.vk.hget(f"user({current_user.id}):current_composition:meta_data", "tokens_used_response", 0)
    return tokens_used_total, tokens_used_prompts, tokens_used_responses

def del_comp_meta_data():
    current_app.vk.delete(f"user({current_user.id}):current_composition:meta_data")


# Global API Use Data

def incr_global_api_use_data(tpm):
    """ INCRBY creates the key-value pair if it does not exist so no new one needs to be created"""
    current_app.vk.hincrby("global:limits:meta_data", "tpm", tpm)
    current_app.vk.hincrby("global:limits:meta_data", "rpm", 1)

def reset_global_api_use_data():
    current_app.vk.hset("global:limits:meta_data", "tpm", 0)
    current_app.vk.hset("global:limits:meta_data", "rpm", 0)
    current_app.vk.hset("global:limits:meta_data", "reset_time", datetime.now().timestamp())

def get_global_api_use_data(key):
    return current_app.vk.hget("global:limits:meta_data", key)


def get_auto_save_inputs(n: int) -> str:
    if 'auto_save_inputs' in session and n in session['auto_save_inputs']:
        return session['auto_save_inputs'][n]
    return ''

def set_auto_save_inputs(n: int, content: str):
    if not 'auto_save_inputs' in session:
        session['auto_save_inputs'] = {}
    session['auto_save_inputs'][n] = content

def reset_auto_save_inputs():
    session['auto_save_inputs'] = {}



def tiktoken_count_tokens(content: str) -> int:
    encoding = tiktoken.encoding_for_model(openai_model_name)
    token_count = len(encoding.encode(content))
    return token_count


## Main Functions for Prompt generation
def process_var_prompt_base_input(input_text: str) -> tuple[list[str], list[str]]:
    pattern = re.compile(r'{{(.*?)}}')
    segments = pattern.split(input_text)

    variable_names = []
    text_segments = []
    
    for i, segment in enumerate(segments):
        if i % 2 == 0: text_segments.append(segment)
        else: variable_names.append(segment.strip())

    for i, variable in enumerate(variable_names):
        if variable == '': variable_names[i] = f'Variable {i+1}'
    
    return text_segments, variable_names # List of each Textsegment between and before Variable places, Variable Name

def create_index_values_prompt_list_from_input(text_segments: list, variable_values: list) -> list:
    """ 
        Returns a list that looks like this:
        [
        index (int, starting at 0),
        []
        ]
    """
    


    if variable_values == []: return [[0,['NO VARIABLES'], text_segments[0]]]

    variable_value_combinations = list(product(*variable_values))

    index_values_prompt_list = []
    i = 0
    for values in variable_value_combinations:
        prompt = ""
        
        for j in range(len(values)): 
            prompt += f'{text_segments[j]}{values[j]}'

        if len(text_segments) > len(values):
            prompt += text_segments[len(values)] 
            
        index_values_prompt_list.append([i, list(values), prompt])
        i += 1

    return index_values_prompt_list


def count_total_tokens_in_prompts_list(prompts_list: list) -> int:
    total = 0
    for prompt in prompts_list:
        total += tiktoken_count_tokens(prompt) 

    return total

async def process_var_prompt(index_values_prompt_list: list):
    
    async def process_single_prompt(index_values_prompt_list):

        index           = index_values_prompt_list[0]
        values          = index_values_prompt_list[1]
        prompt          = index_values_prompt_list[2]
        prompt_tokens   = tiktoken_count_tokens(prompt)

        if (datetime.now().timestamp() - float(get_global_api_use_data("reset_time").decode('utf-8'))) > 60:
            reset_global_api_use_data()

        while True:
            if ((prompt_tokens * 100) + int(get_global_api_use_data("tpm").decode('utf-8')) + 1000 >= openai_model_limit_tpm):
                time_utill_reset = int(datetime.now().timestamp() - float(get_global_api_use_data("reset_time").decode('utf-8')))
                await asyncio.sleep(time_utill_reset)
            elif (int(get_global_api_use_data("rpm").decode('utf-8')) + 3 >= openai_model_limit_rpm):    
                time_utill_reset = int(datetime.now().timestamp() - float(get_global_api_use_data("reset_time").decode('utf-8')))
                await asyncio.sleep(time_utill_reset)
            else: 
                break

        try:
            response = await openai_client.chat.completions.create(
                model= openai_model_name,
                messages=[{"role": "user", "content": prompt}],
            )

            prompt_response = response.choices[0].message.content

            incr_comp_meta_data(
                tokens_used_total = response.usage.total_tokens,
                tokens_used_prompts = response.usage.prompt_tokens,
                tokens_used_response = response.usage.completion_tokens
            )
            incr_global_api_use_data(tpm = response.usage.total_tokens)
            
        except Exception as e: 
            print(f'ERROR - OpenAI API call failed: {e}')
            prompt_response = f'ERROR. Please contact support for help.'

        return [index, values, prompt, prompt_response]
    
    reset_global_api_use_data()
    init_comp_meta_data(prompts_amount=len(index_values_prompt_list))

    tasks                       = [process_single_prompt(index_values_prompt) for index_values_prompt in index_values_prompt_list]
    values_prompt_response_list = await asyncio.gather(*tasks)

    try:
        tokens_used_total, tokens_used_prompts, tokens_used_responses = get_comp_meta_data()
        current_user.token_balance = current_user.token_balance - tokens_used_total
        db.session.commit()
        del_comp_meta_data()
        session['current_compose_step'] = 0

    except Exception as e: print(f'DB Tokens Used update and VK reset failed:\n\n{e}')

    values_prompt_response_list.sort(key=lambda x: x[0])
    for entry in values_prompt_response_list: entry.pop(0)


    return values_prompt_response_list, tokens_used_total, tokens_used_prompts, tokens_used_responses



def register_compose_routes(app):
    
    ## Compose Page Components 

    @app.route('/component/compose/var-prompt/input/<n>', methods=['GET', 'POST'])
    @login_required
    def comp_compose_var_prompt(n):
        try: n = int(n)
        except: abort(404)

        if request.method == 'GET':
            session['current_compose_step'] = n

            if n == 0: 
                return render_template(
                    'components/compose/var_prompt/input_base.html',
                    auto_save_text = get_auto_save_inputs(n)
                )
            elif 0 < n and n <= len(session['compose_data']['variable_names']): 

                return render_template(
                    'components/compose/var_prompt/input_vars.html',
                    auto_save_text          = get_auto_save_inputs(n),
                    current_variable_name   = session['compose_data']['variable_names'][n-1],
                    n                       = n,
                    N                       = len(session['compose_data']['variable_names']),

                )
            
            elif n > len(session['compose_data']['variable_names']):
                return redirect(url_for('comp_compose_var_prompt_confirm'))
            
            else:
                abort(404)
        
        elif request.method == 'POST':

            if n == 0:  # Processing the Base-Prompt
                
                raw_text = request.form['textarea']

                if raw_text.strip() == '': 
                    return redirect(url_for('comp_compose_var_prompt', n=0))
                
                set_auto_save_inputs(n, raw_text)
                text_segments, variable_names = process_var_prompt_base_input(raw_text)
                
                set_text_segemnts(text_segments)
                set_variable_names(variable_names)

            else:  # Processing Variable Values

                raw_text        = request.form['textarea']
                var_seperation  = request.form['var_seperation']

                set_auto_save_inputs(n, raw_text)

                if var_seperation == 'new_line': 
                    var_inputs = raw_text.split('\n')
                    while len(var_inputs) > 0 and var_inputs[-1].strip() == '': var_inputs.pop()

                elif var_seperation == 'comma':      
                    var_inputs = raw_text.split(',')
                    if len(var_inputs) > 0 and var_inputs[-1].strip() == '': var_inputs.pop()

                else:
                    raise ValueError("Clientside variable separation method name not supported")

                var_inputs = [var_input.strip() for var_input in var_inputs]
                current_varabile_name = get_nth_variable_name(n-1)
                set_variable(current_varabile_name, var_inputs)
    
            return redirect(url_for('comp_compose_var_prompt', n=n+1))


    @app.route('/component/compose/var-prompt/confirm')
    @login_required
    def comp_compose_var_prompt_confirm():

        text_segments   = get_del_text_segments()
        variable_names  = get_del_variable_names()
        variable_values = get_del_variables()
        
        index_values_prompt_list = create_index_values_prompt_list_from_input(text_segments, variable_values)

        session['compose_data']['index_values_prompt_list'] = index_values_prompt_list

        prompts_list            = [index_values_prompt[2] for index_values_prompt in index_values_prompt_list]
        prompt_token_count      = count_total_tokens_in_prompts_list(prompts_list)
        response_token_count    = int(round(prompt_token_count * 1.874))
        total_token_count       = prompt_token_count + response_token_count 

        base_text_list = []
        for i, segment in enumerate(text_segments):
            base_text_list.append(segment)
            if i < len(variable_names): base_text_list.append(variable_names[i])

        variable_name_and_values = []
        for i, variable_name in enumerate(variable_names):
            variable_name_and_values.append([variable_name, variable_values[i]])

        base_text = []
        for i, segment in enumerate(text_segments):
            base_text.append(segment)
            if i < len(variable_names): 
                base_text.append('{{ ')
                base_text.append(variable_names[i])
                base_text.append(' }}')
        base_text = ''.join(base_text).strip()
        
        if len(base_text) <= 180:   session['compose_data']['display_text'] = base_text
        else:                       session['compose_data']['display_text'] = base_text[0:180].strip() + '...' 

        return render_template(
            'components/compose/var_prompt/confirm_input.html',
            n                       = session['current_compose_step'],
            prompt_token_count      = token_count_to_string(prompt_token_count),
            response_token_count    = token_count_to_string(response_token_count),
            total_token_count       = token_count_to_string(total_token_count),
            base_text_list          = base_text_list,
            variable_list           = variable_name_and_values,
            prompts_list            = prompts_list,
            prompts_amount          = len(prompts_list),
        )

    @app.route('/component/compose/var-prompt/process/start')
    @login_required
    def comp_compose_var_prompt_process_start():
        return render_template('components/compose/var_prompt/process_input.html')

    @app.route('/component/compose/var-prompt/process/progress_stream')
    @login_required
    def comp_compose_var_prompt_process_progress():
        vk = current_app.vk

        while True: # Wait till up-to-date data is uploaded before streaming
            data_reset = int(vk.get(f'global:user({current_user.id}):request_counts:start_progress_stream') or 0)                           
            if data_reset == 1: 
                vk.set(f'global:user({current_user.id}):request_counts:start_progress_stream', 0)
                break
            time.sleep(0.2)

        def generate():
            prompt_amount           = int(vk.get(f'global:user({current_user.id}):request_counts:prompts_amount') or 0)
            prompts_completed_prev  = 0
            percentage              = 0

            while True:
                prompts_completed = int(vk.get(f'global:user({current_user.id}):request_counts:prompts_completed') or 0)
                total_tokens_used = int(vk.get(f'global:user({current_user.id}):request_counts:tokens_used_total') or 0)

                if prompts_completed_prev != prompts_completed:
                    prompts_completed_prev = prompts_completed
                    percentage = (prompts_completed / prompt_amount) * 100

                    progress = json.dumps({
                        'completed': prompts_completed,
                        'total': prompt_amount,
                        'tokens': total_tokens_used,
                        'percentage': round(percentage)
                    })
                    yield f"data: {progress}\n\n"
                
                time.sleep(0.3)
                if percentage == 100: break
            
        return Response(stream_with_context(generate()), mimetype='text/event-stream')

    @app.route('/component/compose/var-prompt/process/process')
    @login_required
    async def comp_compose_var_prompt_process_process():     

        if current_user.token_balance <= 0: abort(402, description="Insufficient tokens to complete this action.")

        index_values_prompt_list    = session['compose_data']['index_values_prompt_list']
        variable_names              = session['compose_data']['variable_names']
        display_text                = session['compose_data']['display_text']

        values_prompt_response_list, tokens_used_total, tokens_used_prompts, tokens_used_responses = await process_var_prompt(index_values_prompt_list)

        results_table = []
        if variable_names:
            results_table.append(variable_names + ['Prompt', 'Response'])
            for values_prompt_response in values_prompt_response_list:
                row = []
                for value in values_prompt_response[0]: row.append(value)
                row.append(values_prompt_response[1])
                row.append(values_prompt_response[2])
                results_table.append(row)
        else:
            results_table.append(['Prompt', 'Response'])
            results_table.append([values_prompt_response_list[0][1], values_prompt_response_list[0][2]])

        request_id = str(ulid.new())
        new_request = Request(
            id                      = request_id,
            user_id                 = current_user.id,
            tokens_used_total       = tokens_used_total,
            tokens_used_prompts     = tokens_used_prompts,
            tokens_used_responses   = tokens_used_responses,
            prompt_amount           = len(index_values_prompt_list),
            display_text            = display_text,
            data                    = {
                'type':     'var_prompt',
                'version':  1,
                'data': {
                    'variable_names':   variable_names,
                    'results_table' :   results_table,
                }
            }
        )
        db.session.add(new_request)
        db.session.commit()

        session['current_compose_step'] = 0
        reset_auto_save_inputs() 

        preview_list = [key_prompt_response[2] for key_prompt_response in values_prompt_response_list[0:10]]
        preview_list_is_complete = True if len(preview_list) <= 10 else False
        
        return render_template(
            'components/compose/var_prompt/view_results.html',
            preview_list                = preview_list,
            preview_list_is_complete    = preview_list_is_complete,
            download_url                = url_for('download', request_id=request_id),
        )
        
    # User Actions
    @app.route('/component/compose/var-prompt/action/auto-save/<n>', methods=['POST'])
    @login_required
    def comp_compose_var_prompt_auto_save(n):
        try: n = int(n)
        except: abort(404)
        set_auto_save_inputs(n, request.form['textarea'])
        return "Saved"                    
        
    @app.route('/component/compose/var-prompt/action/clear_data/<n>')
    @login_required
    def comp_compose_var_prompt_clear_data(n):
        try: n = int(n)
        except: abort(404)
        reset_auto_save_inputs()
        session['compose_data'] = {}
        return redirect(url_for('comp_compose_var_prompt', n=n))



    @app.route('/download/<request_id>')
    @login_required
    def download(request_id):

        request = Request.query.filter_by(id=request_id).first()
        if not request:                             abort(404)
        if not request.user_id == current_user.id:  abort(403)

        creation_time = request.created_at.astimezone(ZoneInfo(current_user.timezone)).strftime('%Y-%m-%d_%H-%M-%S')
        results_table = request.data.get('data', {}).get('results_table', [])
        if not results_table: abort(500)

        filename = f"{request_id}.csv"
        temp_dir = tempfile.gettempdir()
        filepath = os.path.join(temp_dir, filename)

        with open(filepath, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.writer(csvfile)
            for row in results_table: writer.writerow(row)

        try: return send_file(filepath, mimetype='text/csv', as_attachment=True, download_name=f'RepetioAI_Results_{creation_time}.csv')
        except FileNotFoundError: return {'error': 'File not found'}, 404


