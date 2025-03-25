import re




def is_regex_valid_email(email: str):
    email_regex = r"(^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$)"
    return re.match(email_regex, email)






def token_count_to_string(count: int):
    if count < 10_000:      return str(count)
    return re.sub(r"(?<=\d)(?=(\d{3})+$)", ".", str(count))

def time_delta_to_string(time_delta):
    if   time_delta.days > 0:               
        time_string = f'{time_delta.days}'
        unit_string = 'days'
    elif time_delta.seconds >= 3600:
        time_string = f'{time_delta.seconds // 3600}'
        unit_string = 'hours'
    elif time_delta.seconds >= 60:
        time_string = f'{time_delta.seconds // 60}'
        unit_string = 'minutes'
    else:                                   
        time_string = f'<1'
        unit_string = 'minute'
    return time_string, unit_string



def token_count_to_short_string(n):
        if n < 0:   negative = True
        else:       negative = False

        n = abs(n)

        if n >= 1_000_000_000:  
            n = n / 1_000_000_000
            suffixes = 'B'
        elif n >= 1_000_000:      
            n = n / 1_000_000
            suffixes = 'M'
        elif n >= 1_000:          
            n = n / 1_000
            suffixes = 'K'  
        else:
            suffixes = ''          

        n = str(round(n, 2))[0:4]
        if len(n) > 1 and n[-1] == '.': n = n[0:-1]

        return f'{n}{suffixes}' if not negative else f'-{n}{suffixes}'