#!/usr/bin/env python3
import json
import os
import sys
from jinja2 import Environment, FileSystemLoader


def nl2br(s):
    if s is None:
        return ''
    return str(s).replace('\n', '<br/>')


def tojson(v, indent=None):
    return json.dumps(v, ensure_ascii=False, indent=indent)


def main():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env = Environment(loader=FileSystemLoader(root), autoescape=False)
    env.filters['nl2br'] = nl2br
    env.filters['tojson'] = tojson

    tpl = env.get_template('report_template.html')

    func_index = {
        'api.getUser': {
            'total': 2,
            'passed': 1,
            'by_param': {
                'userId': [
                    {
                        'case_id': 'G-001',
                        'name': '正常获取用户',
                        'scenario_type': '正向',
                        'passed': True,
                        'expected': {'status': 200, 'payload': {'id': 1, 'name': 'Alice'}},
                        'actual_responses': [
                            {
                                'source': 'live',
                                'status': 200,
                                'body': {
                                    'payload': {'id': 1, 'name': 'Alice'},
                                    'responses': {'message': 'ok'}
                                }
                            }
                        ],
                        'diff': ''
                    },
                    {
                        'case_id': 'G-002',
                        'name': '用户不存在',
                        'scenario_type': '负向',
                        'passed': False,
                        'expected': {'status': 404, 'payload': {'error': 'not found'}},
                        'actual_responses': [
                            {
                                'source': 'live',
                                'status': 500,
                                'raw': {'error': 'internal'}
                            }
                        ],
                        'diff': '--- expected\n+++ actual\n@@\n-404\n+500'
                    }
                ]
            }
        }
    }

    perf_summary = {}
    md_parsed = {}

    out = tpl.render(func_index=func_index, perf_summary=perf_summary, md_parsed=md_parsed)
    out_path = os.path.join(root, 'report_demo.html')
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(out)
    print('Wrote demo report to', out_path)


if __name__ == '__main__':
    main()
