from py2assembly import convert


def check(code, target):
    code = '\n'.join(code)
    target = '\n'.join(target)
    converted = convert(code)
    print()
    print('-' * 120)
    print('Python:')
    print(code)
    print('-' * 120)
    print('Assembly:')
    print(converted)
    print('-' * 120)
    # annotation does not need to be checked
    converted = '\n'.join(i.split(';')[0].rstrip() if ';' in i else i for i in converted.split('\n'))
    for unknown, correct in zip(target.splitlines(), converted.splitlines()):
        assert unknown == correct, f'"{unknown}" not "{correct}".'


def test_convert_assign():
    check((
        'a = 15',
    ), (
        '    trap R0,R0,R0',
        '',
        'a data 15'
    ))


def test_convert_assign_again():
    check((
        'a = 15',
        'a = 19',
    ), (
        '    lea R1,19',
        '    store R1,a',
        '    trap R0,R0,R0',
        '',
        'a data 15'
    ))


def test_convert_plus():
    check((
        'a = 15',
        'b = 21',
        'c = a + b',
        'd = a + c',
        'e = a + 6',
        'e = 5 + 3',
    ), (
        '    load R2,a',  # c = a + b
        '    load R3,b',
        '    add R1,R2,R3',
        '    store R1,c',
        '    load R2,a',  # d = a + c
        '    load R3,c',
        '    add R1,R2,R3',
        '    store R1,d',
        '    load R2,a',  # e = a + 6
        '    lea R3,6',
        '    add R1,R2,R3',
        '    store R1,e',
        '    lea R2,5',  # e = 5 + 3
        '    lea R3,3',
        '    add R1,R2,R3',
        '    store R1,e',
        '    trap R0,R0,R0',
        '',
        'a data 15',
        'b data 21',
        'c data 0',
        'd data 0',
    ))


def test_convert_comment():
    # When AST is processing, it does not retain comments by default, so no additional processing is required.
    check((
        'a = 15  # set a to 15',
    ), (
        '    trap R0,R0,R0',
        '',
        'a data 15'
    ))


def test_convert_four_arithmetic_operations():
    check((
        'a = 3',
        'b = 4',
        'c = b - 3',
        'd = c * 5',
        'e = d + 15',
        'f = e / 5',
        'g = 40 / 5',
    ), (

        '    load R2,b',
        '    lea R3,3',
        '    sub R1,R2,R3',
        '    store R1,c',
        '    load R2,c',
        '    lea R3,5',
        '    mul R1,R2,R3',
        '    store R1,d',
        '    load R2,d',
        '    lea R3,15',
        '    add R1,R2,R3',
        '    store R1,e',
        '    load R2,e',
        '    lea R3,5',
        '    div R1,R2,R3',
        '    store R1,f',
        '    lea R2,40',
        '    lea R3,5',
        '    div R1,R2,R3',
        '    store R1,g',
        '    trap R0,R0,R0',
        '',
        'a data 3',
        'b data 4',
        'c data 0',
        'd data 0',
        'e data 0',
        'f data 0',
        'g data 0',
    ))
