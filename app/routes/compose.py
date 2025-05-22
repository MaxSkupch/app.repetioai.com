'''
All Pages and functions related to the compose Pages


TODO 

COMPOSITION DRAFT NEEDS TO BE IMPLEMENTED FROM CONFIRMATION PAGE ONWARDS
ALSO DRAFT NEEDS TO BE CONVERTED TO NON DRAFT VERSION AT SOME POINT


Reasonings:

Have composition draft with only raw inputs and only convert it before sending to the worker queue
- draft keeeps it simple and changes are easy -> one source of truth
- diesected version only used on the confirmation page

'''


import csv
import json
import os
import re
import tempfile
import tiktoken
import time
import ulid
import uuid

from datetime       import datetime
from flask          import render_template, abort, request, redirect, url_for, Response, stream_with_context, current_app, send_file, session, flash
from flask_login    import login_required, current_user
from itertools      import product
from zoneinfo       import ZoneInfo

from app            import db
from app.extensions import openai_client
from app.functions  import token_count_to_string
from app.models     import Request
from app.values     import OPENAI_API_MODEL_NAME


'''
SENDING COMP STRUCTURE


if not 'composition' in session:  # n == 0 so the DB (Valkey) does not get quiried each time -> Faster
    session['composition'] = {
        'job_id': str(uuid.uuid4()),  # Example: '123e4567-e89b-12d3-a456-426614174000'
        'user_id': current_user.id,
        'text_segments': None,  # Example: ['Hello ', ' I hope you are', '']
        'variables': None,  # Example: ['Name', 'Wish']
        'values': {
            # Example: 'Name': ['Alice', 'Bob']
            #          'Wish': ['happy', 'well']
        }
    }

    





'''


def get_from_composition_draft(n):
    composition_draft = session.get('composition_draft', [])
    if n == 0 and len(composition_draft) > 0: 
        return composition_draft[0]
    elif n > 0 and len(composition_draft) > n:
        return composition_draft[n][0]
    return ''

def safe_to_composition_draft(n, raw_text, separator = None):
    if not 'composition_draft' in session: 
        session['composition_draft'] = []
    if not len(session['composition_draft']) > n:  # Fail safe version that allow the user to save a draft for a non-existing input
        session['composition_draft'] += [''] * (n + 1 - len(session['composition_draft']))

    if n == 0: session['composition_draft'][n] = raw_text
    elif n > 0: session['composition_draft'][n] = [raw_text, separator]




def register_compose_routes(app):

    ## Auto Save Routes 

    @app.route('/component/compose/var-prompt/action/auto-save/<n>', methods=['POST'])
    @login_required
    def comp_compose_var_prompt_auto_save(n):
        try: n = int(n)
        except: abort(404)
        safe_to_composition_draft(n, request.form['textarea'])
        return "Saved"                    
        
    @app.route('/component/compose/var-prompt/action/clear_input')
    @login_required
    def comp_compose_var_prompt_clear_input():
        if 'composition_draft' in session: del session['composition_draft']
        return redirect(url_for('comp_compose_var_prompt_input', n=0))

    
    ## Compose Page Components 

    @app.route('/component/compose/var-prompt/input/<n>', methods=['GET', 'POST'])
    @login_required
    def comp_compose_var_prompt_input(n):
        try: n = int(n)
        except: abort(404)

        if request.method == 'GET':
            session['current_composition_step'] = n

            if n == 0: return render_template('components/compose/var_prompt/input_base.html', auto_save_text = get_from_composition_draft(n))

            base_prompt = get_from_composition_draft(0)
            var_names = [var.strip() if var.strip() else f'Variable {i+1}' for i, var in enumerate(re.findall(r'{{(.*?)}}', base_prompt))]
            
            if 0 < n <= len(var_names): return render_template('components/compose/var_prompt/input_vars.html', current_variable_name = var_names[n-1], n = n, N = len(var_names), auto_save_text = get_from_composition_draft(n))
            elif n > len(var_names): return redirect(url_for('comp_compose_var_prompt_confirm'))
    
            abort(404)
        
        elif request.method == 'POST':
            raw_text = request.form['textarea']
            
            if raw_text.strip() == '': return redirect(url_for('comp_compose_var_prompt_input', n=n))
            
            separator = None
            if n > 0:
                separators = {'new_line': '\n', 'comma': ','}
                seperator_name  = request.form['var_seperation']
                if not seperator_name in separators: raise ValueError('Clientside variable separation method name not supported')
                separator = separators[seperator_name]

            safe_to_composition_draft(n, raw_text, separator)
            return redirect(url_for('comp_compose_var_prompt_input', n=n+1))


    @app.route('/component/compose/var-prompt/confirm')
    @login_required
    def comp_compose_var_prompt_confirm():

        if 'composition_draft' not in session or not session['composition_draft']: raise ValueError('No composition draft found in session when requesing confirmation page')
        composition_draft = session['composition_draft']

        text_segments = re.split(r'{{.*?}}', composition_draft[0])
        variables = [var.strip() if var.strip() else f'Variable {i+1}' for i, var in enumerate(re.findall(r'{{(.*?)}}', composition_draft[0]))]
        base_text_list = [text_segments[0]] + [x for pair in zip(variables, text_segments[1:]) for x in pair]  # List so that vars can be higlighted in html.
        
        values = [[value.strip() for value in value_text.split(seperator) if value.strip()] for value_text, seperator in composition_draft[1:]]
        variable_value_pairings = list(zip(variables, values))
        value_combinations = list(product(*values))
        
        if len(text_segments) == 1: prompts = [text_segments[0]]
        else: prompts = [text_segments[0] + ''.join(value + text_segments[i + 1] for i, value in enumerate(combo)) for combo in value_combinations]

        prompt_token_count = sum(len(tiktoken.encoding_for_model(OPENAI_API_MODEL_NAME).encode(prompt)) for prompt in prompts)
        
        return render_template(
            'components/compose/var_prompt/confirm_input.html',
            n                       = len(composition_draft),
            base_text_list          = base_text_list,
            variable_value_pairings = variable_value_pairings,
            prompts_list            = prompts,
            prompts_amount          = len(prompts),
            prompt_token_count      = token_count_to_string(prompt_token_count),
            response_token_count    = token_count_to_string(round(prompt_token_count * 1.8)),  # TODO: Track this in the future and adjust it
            total_token_count       = token_count_to_string(round(prompt_token_count * 2.8)),  # TODO: Track this in the future and adjust it
        )

    @app.route('/component/compose/var-prompt/process/start')
    @login_required
    def comp_compose_var_prompt_process_start():
        ''' Get then delete the composition draft from the session, upload the finalized composition to the queue and redirect to the progress page. '''

        # TODO Check if the token count is too high for the model (context window)
        # TODO Check if the token count is too high for the user 
        # If to high -> redirect to the confirmation page with a flah warning, and do so before popping the session

        composition_draft = session.pop('composition_draft', None)
        if not composition_draft: abort(404)
        session['current_composition_step'] = 0

        composition = {
            'job_id': str(uuid.uuid4()),  # Example: '123e4567-e89b-12d3-a456-426614174000'
            'user_id': current_user.id,
            'text_segments': re.split(r'{{.*?}}', composition_draft[0]),
            'variables': [var.strip() if var.strip() else f'Variable {i+1}' for i, var in enumerate(re.findall(r'{{(.*?)}}', composition_draft[0]))],  
            'values': [[value.strip() for value in value_text.split(seperator) if value.strip()] for value_text, seperator in composition_draft[1:]],
        } 

        # All VK entries are deleted by the Request Processor when the job is completed
        current_app.vk.set(f'job:data:{composition['job_id']}', json.dumps(composition), ex=60*60*24*7)
        current_app.vk.set(f'job:status:{composition['job_id']}', 'Pending...', ex=60*60*24*7)
        current_app.vk.set(f'job:progress:{composition['job_id']}', 0.0, ex=60*60*24*7)
        current_app.vk.set(f'job:tokens:{composition['job_id']}', 0, ex=60*60*24*7)
        current_app.vk.lpush('jobs:pending', composition['job_id'])

        return render_template('components/compose/var_prompt/process_input.html', job_id = composition['job_id'])
    

    @app.route('/component/compose/var-prompt/process/progress_stream/<job_id>')
    @login_required
    def comp_compose_var_prompt_process_progress(job_id):
        def generate(tokens_ref=0):
            while True:
                status = current_app.vk.get(f'job:status:{job_id}')
                if status and status == 'Complete':  # Yield a final message and break to end the stream.
                    yield f'data: {json.dumps({"status": status, "progress": 100, "tokens": current_app.vk.get(f"job:tokens:{job_id}")})}\n\n'
                    break
                tokens = current_app.vk.get(f'job:tokens:{job_id}')
                if tokens != tokens_ref:
                    tokens_ref = tokens
                    progress = round(float(current_app.vk.get(f"job:progress:{job_id}") or 0.0))
                    yield f'data: {json.dumps({"status": status, "progress": progress, "tokens": tokens})}\n\n'
                time.sleep(0.1)
    
        return Response(stream_with_context(generate()), mimetype='text/event-stream')
    
    
    @app.route('/component/compose/var-prompt/process/complete/<job_id>')
    @login_required
    def comp_compose_var_prompt_process_complete(job_id): 
        ''' Get the Request ID from the job ID, and then display the results. '''

        # Wait until the job is complete. Maybe a better way to do this is to use a websocket or something similar but for POST_MVP
        while current_app.vk.get(f'job:status:{job_id}') != 'Complete': time.sleep(0.2)

        # Gets Request ID from the job ID, and then checks if the currently logged in user is allowed to see the results  
        request_id = current_app.vk.get(f'job:request_id:{job_id}')
        print(job_id)
        print(request_id)
        if not request_id: abort(404)
        current_app.vk.delete(f'job:request_id:{job_id}')
        request = Request.query.filter_by(id=request_id).first()
        if not request.user_id == current_user.id: abort(401)

        ## POST_MVP Add a preview of the results here
        return render_template('components/compose/var_prompt/view_results.html', download_url = url_for('download', request_id=request_id))
                         

    @app.route('/download/<request_id>')
    @login_required
    def download(request_id):

        request = Request.query.filter_by(id=request_id).first()
        if not request:                             abort(404)
        if not request.user_id == current_user.id:  abort(403)

        creation_time = request.created_at.astimezone(ZoneInfo(current_user.timezone)).strftime('%Y-%m-%d_%H-%M-%S')
        results_table = request.data.get('data', {}).get('results_table', [])
        if not results_table: abort(500)

        filename = f'{request_id}.csv'
        temp_dir = tempfile.gettempdir()
        filepath = os.path.join(temp_dir, filename)

        with open(filepath, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.writer(csvfile)
            for row in results_table: writer.writerow(row)

        try: return send_file(filepath, mimetype='text/csv', as_attachment=True, download_name=f'RepetioAI_Results_{creation_time}.csv')
        except FileNotFoundError: return {'error': 'File not found'}, 404


