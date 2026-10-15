"""Translate each wire protocol into the engine's existing completed event."""
import json


def payload(profile, request, output_limit):
    model = request['model']; schema = request['schema']; prompt = request['prompt']
    protocol = profile['protocol']
    if protocol == 'responses':
        return '/responses', {'model': model, 'input': prompt, 'store': False, 'max_output_tokens': output_limit,
                              'text': {'format': {'type': 'json_schema', 'name': 'waypoint', 'strict': True, 'schema': schema}}}
    if protocol == 'anthropic':
        return '/messages', {'model': model, 'max_tokens': output_limit, 'messages': [{'role': 'user', 'content': prompt}],
                             'tools': [{'name': 'waypoint_result', 'description': '返回工作流要求的 JSON 对象，不执行外部操作。', 'input_schema': schema}],
                             'tool_choice': {'type': 'tool', 'name': 'waypoint_result'}}
    prompt += '\n只返回一个 JSON 对象，不加代码围栏或额外文字。严格遵守此 JSON Schema：\n' + json.dumps(schema, ensure_ascii=False)
    format_ = {'type': 'json_object'} if profile.get('json_mode') == 'object' else {
        'type': 'json_schema', 'json_schema': {'name': 'waypoint', 'strict': True, 'schema': schema}}
    return '/chat/completions', {'model': model, 'messages': [{'role': 'user', 'content': prompt}],
                                  profile.get('token_parameter', 'max_tokens'): output_limit, 'response_format': format_, 'stream': False}


def tokens(value): return value if type(value) is int and value >= 0 else None


def decode(protocol, data):
    usage = data.get('usage') or {}
    if not isinstance(usage, dict): usage = {}
    input_ = tokens(usage.get('input_tokens' if protocol != 'chat' else 'prompt_tokens'))
    output = tokens(usage.get('output_tokens' if protocol != 'chat' else 'completion_tokens'))
    if protocol == 'anthropic':
        # Cache writes use a different tariff and cannot silently use the normal rate.
        if usage.get('cache_creation_input_tokens'): input_ = None
        elif input_ is not None:
            cached = tokens(usage.get('cache_read_input_tokens', 0))
            input_ = input_ + cached if cached is not None else None
        blocks = [b for b in data.get('content', []) if b.get('type') == 'tool_use' and b.get('name') == 'waypoint_result']
        complete = data.get('stop_reason') == 'tool_use' and len(blocks) == 1 and isinstance(blocks[0].get('input'), dict)
        text = json.dumps(blocks[0]['input'], ensure_ascii=False) if complete else ''
    elif protocol == 'chat':
        choices = data.get('choices') or []
        choice = choices[0] if len(choices) == 1 else {}
        text = (choice.get('message') or {}).get('content') or ''
        complete = choice.get('finish_reason') == 'stop' and isinstance(text, str) and bool(text)
    else:
        text = ''.join(part.get('text', '') for item in data.get('output', []) for part in item.get('content', []) if part.get('type') == 'output_text')
        complete = data.get('status') == 'completed' and bool(text)
    return text if isinstance(text, str) else '', {'input_tokens': input_, 'output_tokens': output}, complete
