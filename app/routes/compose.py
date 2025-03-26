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


def register_compose_routes(app):
    
    ## Compose Page Components 

    @app.route('/component/compose/var-prompt/input/<n>', methods=['GET', 'POST'])
    @login_required
    def comp_compose_var_prompt(n):

        if n == 0 and not 'composition' in session:  # n == 0 so the DB (Valkey) does not get quiried each time -> Faster
            session['composition'] = {
                'job_id': None,  # Example: '123e4567-e89b-12d3-a456-426614174000'
                'text_segments': None,  # Example: ['Hello ", " I hope you are", ""]
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

            if n == 0:  return render_template('components/compose/var_prompt/input_base.html')
            
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

                if var_seperation not in separators: raise ValueError("Clientside variable separation method name not supported")
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

        # Upload request to 



        return render_template('components/compose/var_prompt/process_input.html')
    


#### EVERYTHING BELOW NEEDS TO BE REWRITTEN

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

        preview_list = [key_prompt_response[2] for key_prompt_response in values_prompt_response_list[0:10]]
        preview_list_is_complete = True if len(preview_list) <= 10 else False
        
        return render_template(
            'components/compose/var_prompt/view_results.html',
            preview_list                = preview_list,
            preview_list_is_complete    = preview_list_is_complete,
            download_url                = url_for('download', request_id=request_id),
        )
                         
        
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


