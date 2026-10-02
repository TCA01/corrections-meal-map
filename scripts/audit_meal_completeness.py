import argparse, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from production.completeness_audit import audit_dataset
from production.io import atomic_json
from production.web_bridge import tree_digest

def main():
    sys.stdout.reconfigure(encoding='utf-8')
    args=argparse.ArgumentParser()
    args.add_argument('--run')
    args.add_argument('--output',default='data/production/reports/meal_completeness_audit.json')
    options=args.parse_args()
    root=Path(__file__).resolve().parents[1]
    production=root/'data/production'
    run=root/options.run if options.run else production/json.loads((production/'current.json').read_text())['run_path']
    before=tree_digest(run)
    report=audit_dataset(root,run)
    assert tree_digest(run)==before, 'Audit mutated immutable run'
    report['immutable_run_sha256']=before
    atomic_json(root/options.output,report)
    print(json.dumps({k:v for k,v in report.items() if k not in
                     ('suspicious_documents','incomplete_source_ranges','identical_three_meal_days','golden_validation')},ensure_ascii=False))
    print('Suspicious documents:',len(report['suspicious_documents']), 'incomplete slots:',len(report['incomplete_source_ranges']))
    metrics={k:v for k,v in report['golden_validation'].items() if k not in ('slots','public_ready_validation')}
    metrics['public_ready_validation']={k:v for k,v in report['golden_validation']['public_ready_validation'].items() if k!='slots'}
    print('Golden:',json.dumps(metrics))

if __name__=='__main__':
    main()
