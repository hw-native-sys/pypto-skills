"""Update a cloud task by number or stable ID. Read the partial patch from stdin."""
import argparse
import json
import re
import sys
import uuid
from urllib.parse import quote

from create_task import APIError, DEFAULT_API, WorkflowError, api, api_origin

FIELDS = {'title', 'description', 'analysis', 'notes', 'status', 'priority', 'owner',
          'owner_user_id', 'subject', 'parent_id', 'dependency_ids', 'pr_urls',
          'issue_urls', 'todos', 'attachment_ids', 'doc_paths', 'expected_updated_at'}


def update(args, patch):
    if not isinstance(patch, dict) or not (patch.keys() - {'expected_updated_at'}):
        raise WorkflowError('请通过 stdin JSON 提供需要修改的字段')
    if patch.keys() - FIELDS:
        raise WorkflowError('不支持修改字段：' + '、'.join(sorted(patch.keys() - FIELDS)))
    identifier = args.identifier.strip()
    if not re.fullmatch(r'[1-9][0-9]*(?:\.[1-9][0-9]*)*', identifier):
        try:
            identifier = str(uuid.UUID(identifier))
        except ValueError:
            raise WorkflowError('请提供完整任务编号或稳定任务 ID') from None
    base = api_origin(args.api_url)
    project = getattr(args,'project','pypto')
    query = '?project=' + project if project != 'pypto' else ''
    metadata = api(base, 'GET', '/api/tasks'+query)
    if project != 'pypto' and (metadata.get('project') or {}).get('id') != project:
        raise WorkflowError('API 未确认所选项目空间，停止更新')
    tasks = metadata['tasks']
    matches = [task for task in tasks if task['id'] == identifier or task['number'] == identifier]
    if len(matches) != 1:
        raise WorkflowError('任务编号或 ID 不存在或无法唯一定位，请重新读取确认')
    current = matches[0]
    if 'expected_updated_at' in patch and patch['expected_updated_at'] != current['updated_at']:
        raise WorkflowError('任务已更新，请重新读取并保留他人的最新修改')
    payload = {**patch, 'expected_updated_at': current['updated_at']}
    try:
        result = api(base, 'PATCH', '/api/tasks/' + quote(current['id'], safe='')+query, payload)
    except APIError as error:
        if error.status is not None and 400 <= error.status < 500:
            raise WorkflowError(f'任务更新被拒绝：{error}') from None
        raise WorkflowError(f'任务更新结果未确认：{error}。请重新读取核对，不要直接重复 PATCH。') from None
    task = result.get('task')
    if not isinstance(task, dict) or task.get('id') != current['id']:
        raise WorkflowError('API 返回结果未确认，请重新读取核对，不要重复 PATCH')
    return {'task': task, 'task_url': args.website_url.rstrip('/') + '/?' + ('project='+project+'&' if project != 'pypto' else '') + 'task=' + quote(task['id'], safe='')}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('identifier', help='完整任务编号（例如 3.2）或稳定任务 ID')
    parser.add_argument('--project', choices=['pypto','pypto-lib','serving','simpler'], default='pypto', help='任务所在项目空间')
    parser.add_argument('--api-url', default=DEFAULT_API)
    parser.add_argument('--website-url', default=DEFAULT_API)
    args = parser.parse_args()
    try:
        result = update(args, json.load(sys.stdin))
    except (WorkflowError, OSError, ValueError, TypeError, KeyError) as error:
        print(json.dumps({'error': str(error)}, ensure_ascii=False), file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    sys.exit(main())
