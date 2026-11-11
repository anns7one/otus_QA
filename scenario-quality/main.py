import argparse
import json

from generate_cases import OUTPUT_PATH, REQUIREMENT_PATH, check_review, generate_cases, suite_coverage
from ollama_client import prepare_ollama


def run(reuse_cases):
    from quality_model import predict, train
    from report import build_report

    requirement = REQUIREMENT_PATH.read_text(encoding="utf-8")
    review = check_review(requirement)
    if reuse_cases and OUTPUT_PATH.exists():
        cases = json.loads(OUTPUT_PATH.read_text(encoding="utf-8"))
        print(f"Взяты готовые кейсы: {len(cases)}")
    else:
        prepare_ollama()
        cases = generate_cases(requirement, review["field_rules"])
        OUTPUT_PATH.parent.mkdir(exist_ok=True)
        OUTPUT_PATH.write_text(json.dumps(cases, ensure_ascii=False, indent=2), encoding="utf-8")
    coverage = suite_coverage(cases, requirement)
    print("Покрытие обязательных проверок:", coverage)
    net, training = train()
    predictions = predict(net, cases, requirement)
    build_report(cases, predictions, review, coverage, training)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Генерация тест-кейсов и оценка их качества")
    commands = parser.add_subparsers(dest="command", required=True)
    run_parser = commands.add_parser("run", help="сгенерировать кейсы, обучить модель, построить отчёт")
    run_parser.add_argument("--reuse-cases", action="store_true", help="не генерировать кейсы, взять output/test_cases.json")
    commands.add_parser("build-dataset", help="сгенерировать датасет для обучения модели (долго)")
    args = parser.parse_args()
    if args.command == "run":
        run(args.reuse_cases)
    else:
        import build_dataset

        build_dataset.main()
