from flask          import render_template, session, request, flash, redirect, url_for
from flask_login    import login_required, current_user
from flask_mail     import Message

from app            import mail, db
from app.functions  import is_regex_valid_email
from app.models     import User

def register_account_page_routes(app):

    @app.route('/account/update/personal_information', methods=['POST'])
    @login_required
    def auth_update_personal_information():
        first_name  = request.form['firstname'].strip()
        last_name   = request.form['lastname'].strip()

        update = True

        if not first_name or not last_name:
            flash('All fields are required.')
            update = False

        if len(first_name) > 60:
            flash('First name cannot be longer than 60 characters.')
            update = False

        if len(last_name) > 60:
            flash('Last name cannot be longer than 60 characters.')
            update = False

        if not update: return redirect( url_for('comp_account_personal_information'))

        current_user.first_name = first_name
        current_user.last_name = last_name
        db.session.commit()
        flash('Personal information was updated successfully.')

        return redirect( url_for('comp_account_personal_information'))

    @app.route('/component/account/personal_information')
    @login_required
    def comp_account_personal_information():
        return render_template(
            'components/account/personal_information.html',
            first_name           = current_user.first_name,
            last_name            = current_user.last_name,
        )

        

    @app.route('/account/update/email', methods=['POST'])
    @login_required
    def auth_update_email():
        new_email  = request.form['email'].strip()

        update = True

        if new_email == current_user.email:
            flash('The new email address is the same as the old one.')
            return redirect(url_for('comp_account_update_email_cancel'))
        
        elif not is_regex_valid_email(new_email):
            flash('Invalid email format.')
            update = False

        elif len(new_email) > 150:
            flash('Email cannot be longer than 150 characters.')
            update = False
        
        elif User.query.filter_by(email=new_email).first():
            flash('Email is already being used.')
            update = False

        if not update: return redirect(url_for('comp_account_update_email_cancel'))

        verification_token = app.url_serializer.dumps({'user_id': current_user.id, 'new_email': new_email}, salt='email-change') # TODO
        verification_url = url_for('auth_verify_email_change', verification_token=verification_token, _external=True)

        msg = Message('Verify Email Change', recipients=[new_email])
        msg.body = f'Click the following link to verify your new email: {verification_url}'
        mail.send(msg)

        flash('Request successful. Please complete the update by opening the verification link sent to your new email.')
        return redirect(url_for('comp_account_update_email_awaiting'))


    @app.route('/component/account/update_email/awaiting')
    @login_required
    def comp_account_update_email_awaiting():
        return render_template('components/account/update_email_awaiting.html')

    @app.route('/component/account/update_emai/cancel')
    @login_required
    def comp_account_update_email_cancel():
        return render_template('components/account/update_email_cancel.html', email = current_user.email)


    @app.route('/verify-email-change/<verification_token>')
    def auth_verify_email_change(verification_token):
        try:
            data = app.url_serializer.loads(verification_token, salt='email-change', max_age=3600) # TODO Check Salt
            user = User.query.get(data['user_id'])
            new_email = data['new_email']

            if user and user.email != new_email:
                user.email = new_email
                db.session.commit()
                flash('Email updated successfully.')
            else:
                flash('Invalid or expired link.')
        except:
            flash('Invalid or expired link.')

        session['current_window'] = 'dash_account'
        return redirect(url_for('dash_base'))

