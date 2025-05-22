import re




def is_regex_valid_email(email: str):
    email_regex = r'(^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$)'
    return re.match(email_regex, email)






def token_count_to_string(count: int) -> str:
    if count < 10_000:      return str(count)
    return re.sub(r"(?<=\d)(?=(\d{3})+$)", ".", str(count))
    

def token_count_to_short_string(count: int) -> str:
    if count >= 0:
        if   count <             1_000_000_000: return f'{count:,d}'
        elif count <         1_000_000_000_000: return f'{count / 1_000_000_000:.2f}B'
        elif count <     1_000_000_000_000_000: return f'{count / 1_000_000_000_000:.2f}T'
        elif count < 1_000_000_000_000_000_000: return f'{count / 1_000_000_000_000_000:.2f}Q'
        else:                                   return  'Quintillion'
        
    else:
        return 'Negative'
        



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








if __name__ == '__main__':


    # Testin of token_count_to_short_string function
    tests = {
                                1: '1',
                               10: '10',
                              100: '100',
                            1_000: '1,000',
                           10_000: '10,000',
                          100_000: '100,000',
                        1_000_000: '1,000,000',
                       10_000_000: '10,000,000',
                      100_000_000: '100,000,000',
                    1_000_000_000: '1.00B',
                   10_000_000_000: '10.00B',
                  100_000_000_000: '100.00B',
                1_000_000_000_000: '1.00T',
               10_000_000_000_000: '10.00T',
              100_000_000_000_000: '100.00T',
            1_000_000_000_000_000: '1.00Q',
           10_000_000_000_000_000: '10.00Q',
          100_000_000_000_000_000: '100.00Q',
        1_000_000_000_000_000_000: 'Quintillion',
        # Max Number saved as Bigint in PG: 9_223_372_036_854_775_808
                               -1: 'Negative',
                              -10: 'Negative',
                             -100: 'Negative',
                           -1_000: 'Negative',
                          -10_000: 'Negative',
                         -100_000: 'Negative',
                       -1_000_000: 'Negative',
                      -10_000_000: 'Negative',
                     -100_000_000: 'Negative',
    }
    for input, output in tests.items():
        if token_count_to_short_string(input) != output:
            print(f'Error: {input} -> {token_count_to_short_string(input)} (expected: {output})')
