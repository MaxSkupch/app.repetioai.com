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
from app.models     import UserSubscription, Request
from app.values     import openai_model_name, openai_model_limit_context_window


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
            if n == 0:  
                return render_template('components/compose/var_prompt/input_base.html', auto_save_text = get_from_composition_draft(n))

            base_prompt = get_from_composition_draft(0)
            var_names = [var.strip() if var.strip() else f'Variable {i+1}' for i, var in enumerate(re.findall(r'{{(.*?)}}', base_prompt))]
            
            if 0 < n <= len(var_names): 
                return render_template('components/compose/var_prompt/input_vars.html', current_variable_name = var_names[n-1], n = n, N = len(var_names), auto_save_text = get_from_composition_draft(n))
            
            elif n > len(var_names): 
                return redirect(url_for('comp_compose_var_prompt_confirm'))
    
            abort(404)
        
        elif request.method == 'POST':
            raw_text = request.form['textarea']
            
            if raw_text.strip() == '':
                return redirect(url_for('comp_compose_var_prompt_input', n=n))
            
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

        if not 'composition_draft' in session: raise ValueError('No composition draft found in session when requesing confirmation page')
        composition_draft = session['composition_draft']
        if len(composition_draft) == 0: raise ValueError('Empty composition draft found in session when requesing confirmation page')
        
        composition = {
            'job_id': str(uuid.uuid4()),  # Example: '123e4567-e89b-12d3-a456-426614174000'
            'user_id': current_user.id,
            'text_segments': re.split(r'{{.*?}}', composition_draft[0]),
            'variables': [var.strip() if var.strip() else f'Variable {i+1}' for i, var in enumerate(re.findall(r'{{(.*?)}}', composition_draft[0]))],  
            'values': [],
        } 
        
        for values_text, seperator in composition_draft[1:]: 
            values_list = [x.strip() for x in values_text.split(seperator) if x]
            composition['values'].append(values_list)
    
            
        ### TODO CONTINUE HERE

                    
        '''
        session['composition']['values'][session['composition']['variables'][n-1]] = values

        value_combinations = list(product(*session['composition']['values'].values()))
        text_segments = session['composition']['text_segments']
        prompts = [text_segments[0] + ''.join(val + text_segments[i + 1] for i, val in enumerate(combo)) for combo in value_combinations]
        
        prompt_token_count = sum(len(tiktoken.encoding_for_model(openai_model_name).encode(prompt)) for prompt in prompts)
        # TODO Check Context window len


        base_text_list = [text_segments[0]] + [x for pair in zip(session['composition']['variables'], text_segments[1:]) for x in pair]  # List so that vars can be higlighted in html
        '''
        return render_template(
            'components/compose/var_prompt/confirm_input.html',
            n                       = len(session['composition']['variables']) + 1,
            prompt_token_count      = token_count_to_string(prompt_token_count),
            response_token_count    = token_count_to_string(prompt_token_count * 1.874),
            total_token_count       = token_count_to_string(prompt_token_count * 2.874),
            base_text_list          = base_text_list,
            variable_dict           = session['composition', 'values'],
            prompts_list            = prompts,
            prompts_amount          = len(prompts),
        )

    @app.route('/component/compose/var-prompt/process/start')
    @login_required
    def comp_compose_var_prompt_process_start():

        if current_user.token_balance <= session['composition']['prompt_tokens']:
            flash("Your token balance is too low. Please upgrade your account by clicking your token balance in the side menu, or wait for it to reset at the end of the billing period.") 
            return redirect(url_for("comp_compose_var_prompt_confirm"))
        
        composition = session.pop('composition')

        current_app.vk.set(f'jobs:data:{composition['job_id']}', json.dumps(composition))
        current_app.vk.set(f'jobs:status:{composition['job_id']}', 'Pending...')
        current_app.vk.set(f'jobs:progress:{composition['job_id']}', 0.0)
        current_app.vk.set(f'jobs:tokens:{composition['job_id']}', 0)
        current_app.vk.lpush('jobs:pending', composition['job_id'])

        return render_template('components/compose/var_prompt/process_input.html', job_id = composition['job_id'])
    

    @app.route('/component/compose/var-prompt/process/progress_stream/<job_id>')
    @login_required
    def comp_compose_var_prompt_process_progress(job_id):
        def generate(tokens_ref = 0):
            while (status := current_app.vk.get(f'jobs:status:{job_id}')) != 'Complete':
                if (tokens := current_app.vk.get(f'jobs:tokens:{job_id}')) != tokens_ref:
                    tokens_ref = tokens
                    yield f'data: {json.dumps({'status': status, 'progress': int(current_app.vk.get(f'jobs:progress:{job_id}') or 0), 'tokens': tokens})}\n\n'
                time.sleep(0.1)
            
        return Response(stream_with_context(generate()), mimetype='text/event-stream')


    
    @app.route('/component/compose/var-prompt/process/complete/<job_id>')
    @login_required
    def comp_compose_var_prompt_process_complete(job_id):   
        request = Request.query.get(current_app.vk.get(f'jobs:request_id:{job_id}'))
        current_app.vk.delete(f'jobs:request_id:{job_id}')

        if not request.user_id == current_user.id: abort(401)

        ## Continue from here


        return render_template(
            'components/compose/var_prompt/view_results.html',
            preview_list                = preview_list,
            preview_list_is_complete    = preview_list_is_complete,
            download_url                = url_for('download', request_id=request_id),
        )
                         
#### EVERYTHING BELOW NEEDS TO BE REWRITTEN

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


    