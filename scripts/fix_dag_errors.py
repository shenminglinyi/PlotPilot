#!/usr/bin/env python
"""修复 DAG 验证错误的脚本

运行方式:
  python scripts/fix_dag_errors.py
"""
import sys
import json
from pathlib import Path

# 添加项目根目录到路径
root = Path(__file__).parent.parent
sys.path.insert(0, str(root))

from infrastructure.persistence.database.connection import get_database
from application.engine.dag.validator import DAGValidator
from application.engine.dag.models import DAGDefinition, NodeDefinition, EdgeDefinition

def main():
    print('=== DAG 错误修复脚本 ===\n')

    db = get_database()
    row = db.fetch_one('SELECT id, nodes_json, edges_json FROM dag_versions LIMIT 1')

    if not row:
        print('❌ 数据库中没有 DAG 定义')
        return

    nodes = json.loads(row['nodes_json'])
    edges = json.loads(row['edges_json'])

    print(f'当前 DAG: {len(nodes)} 个节点, {len(edges)} 条边\n')

    # 修复错误 6: 添加熔断器打开边
    print('修复错误 6: 添加熔断器打开边')
    circuit_open_exists = any(
        e['source'] == 'gw_circuit' and e.get('condition') == 'on_breaker_open'
        for e in edges
    )
    if not circuit_open_exists:
        edges.append({
            'id': f'edge_{len(edges)+1}',
            'source': 'gw_circuit',
            'target': 'gw_retry',
            'condition': 'on_breaker_open',
            'source_port': '',
            'target_port': ''
        })
        print('  ✅ 添加: gw_circuit --[on_breaker_open]--> gw_retry\n')

    # 修复错误 7: 审阅网关作为终节点，不需要出边
    print('修复错误 7: 审阅网关作为终节点')
    # 移除可能存在的错误边（gw_review → ctx_memory）
    edges_before = len(edges)
    edges = [e for e in edges if not (e['source'] == 'gw_review' and e['target'] == 'ctx_memory')]
    if len(edges) < edges_before:
        print('  ✅ 移除了错误的边: gw_review → ctx_memory\n')
    else:
        print('  ℹ️  审阅网关已作为终节点，无需出边\n')

    # 修复端口类型不兼容问题
    print('修复端口类型不兼容:')
    print('  ⚠️  这需要修改节点端口定义或边的连接逻辑')
    print('  建议:')
    print('    1. 扩展 exec_writer.context 端口接受 list/json 类型')
    print('    2. 扩展 gw_review.content 端口接受 list/json 类型')
    print('    3. 检查 val_foreshadow → val_kg_infer 的连接是否正确\n')

    # 保存
    try:
        db.execute(
            'UPDATE dag_versions SET edges_json = ?, updated_at = datetime("now") WHERE id = ?',
            (json.dumps(edges, ensure_ascii=False), row['id'])
        )
        db.commit()
        print('✅ 已保存修改\n')
    except Exception as e:
        print(f'❌ 保存失败: {e}\n')
        return

    # 验证
    print('重新验证 DAG...')
    try:
        nodes_objs = [NodeDefinition(**n) for n in nodes]
        edges_objs = [EdgeDefinition(**e) for e in edges]

        dag = DAGDefinition(
            id=row['id'],
            name='单幕全流程',
            nodes=nodes_objs,
            edges=edges_objs
        )

        validator = DAGValidator()
        result = validator.validate(dag)

        print(f'\n验证结果: {result.summary}\n')

        if result.errors:
            print(f'剩余错误 ({len(result.errors)}):')
            for err in result.errors:
                print(f'  ❌ {err}')

        if result.warnings:
            print(f'\n警告 ({len(result.warnings)}):')
            for warn in result.warnings[:3]:
                print(f'  ⚠️  {warn}')

        if result.is_valid:
            print('\n🎉 DAG 验证通过，可以执行了！')
        else:
            print('\n⚠️  还有错误需要处理，请查看上面的错误列表')

    except Exception as e:
        print(f'❌ 验证失败: {e}')

if __name__ == '__main__':
    main()
