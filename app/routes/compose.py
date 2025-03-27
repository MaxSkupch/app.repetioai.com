'''
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



response_data = {'response': 'API response here'}  # Example API response
redis_client.hset(f'responses:{session_id}', index, json.dumps(response_data))


Get Data---

# Retrieve all responses for the session
responses = redis_client.hgetall(f'responses:{session_id}')

# Sort responses by index (keys)
sorted_responses = sorted(responses.items(), key=lambda x: int(x[0]))

# Convert from Redis format (bytes) to usable Python objects
ordered_responses = [json.loads(value.decode()) for _, value in sorted_responses]
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
from app.values     import openai_model_name, openai_model_limit_rpm, openai_model_limit_tpm



#session['compose_data'] = {
#                    'text_segments':    text_segments,
#                    'variable_names':   variable_names,
#                    'variable_values':  [], # list of lists of variable-values
#                }


def register_compose_routes(app):
    
    ## Compose Page Components 

    @app.route('/component/compose/var-prompt/input/<n>', methods=['GET', 'POST'])
    @login_required
    def comp_compose_var_prompt(n):

        if n == 0 and not 'composition' in session:  # n == 0 so the DB (Valkey) does not get quiried each time -> Faster
            session['composition'] = {
                'job_id': str(uuid.uuid4()),  # Example: '123e4567-e89b-12d3-a456-426614174000'
                'user_id': current_user.id,
                'prompt_tokens': 0,
                'text_segments': None,  # Example: ['Hello ', ' I hope you are', '']
                'variables': None,  # Example: ['Name', 'Wish']
                'values': {
                    # Example: 'Name': ['Alice', 'Bob']
                    #          'Wish': ['happy', 'well']
                }
            }

        try: n = int(n)
        except: abort(404)

        if request.method == 'GET':
            var_amount = len(session['composition']['variables'])

            if n == 0:  return render_template('components/compose/var_prompt/input_base.html', auto_save_text = auto_save_text)
            
            elif 0 < n <= var_amount: 
                return render_template(
                    'components/compose/var_prompt/input_vars.html',
                    current_variable_name = session['composition']['variables'][n-1],
                    n = n, N = var_amount,
                )
            
            elif n == var_amount + 1: return redirect(url_for('comp_compose_var_prompt_confirm'))
    
            else: abort(404)
        
        elif request.method == 'POST':

            if n == 0:  # Processing the Base-Prompt

                raw_text = request.form['textarea']

                if raw_text.strip() == '': return redirect(url_for('comp_compose_var_prompt', n=0))
                
                session['composition']['text_segments'] = re.split(r'{{.*?}}', raw_text)
                session['composition']['variables'] = [var.strip() if var.strip() else f'Variable {i+1}' for i, var in enumerate(re.findall(r'{{(.*?)}}', raw_text))]               

            else:  # Processing Variable Values

                raw_text        = request.form['textarea']
                var_seperation  = request.form['var_seperation']
                separators      = {'new_line': '\n', 'comma': ','}

                if var_seperation not in separators: raise ValueError('Clientside variable separation method name not supported')
                values = [x.strip() for x in raw_text.split(separators[var_seperation]) if x]

                session['composition']['values'][session['composition']['variables'][n-1]] = values
    
            return redirect(url_for('comp_compose_var_prompt', n=n+1))


    @app.route('/component/compose/var-prompt/confirm')
    @login_required
    def comp_compose_var_prompt_confirm():

        value_combinations = list(product(*session['composition']['values'].values()))
        text_segments = session['composition']['text_segments']
        prompts = [text_segments[0] + ''.join(val + text_segments[i + 1] for i, val in enumerate(combo)) for combo in value_combinations]
        
        prompt_token_count = sum(len(tiktoken.encoding_for_model(openai_model_name).encode(prompt)) for prompt in prompts)
        response_token_count    = int(round(prompt_token_count * 1.874))
        total_token_count       = prompt_token_count + response_token_count 
        session['composition']['prompt_tokens'] = prompt_token_count

        base_text_list = [text_segments[0]] + [x for pair in zip(session['composition']['variables'], text_segments[1:]) for x in pair]  # List so that vars can be higlighted in html

        return render_template(
            'components/compose/var_prompt/confirm_input.html',
            n                       = len(session['composition']['variables']) + 1,
            prompt_token_count      = token_count_to_string(prompt_token_count),
            response_token_count    = token_count_to_string(response_token_count),
            total_token_count       = token_count_to_string(total_token_count),
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