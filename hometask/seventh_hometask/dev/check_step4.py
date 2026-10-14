import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # prompt_generator/evaluator живут в корне ДЗ, не в dev/
sys.stdout.reconfigure(encoding="utf-8")

from prompt_generator import generate_all_prompts, load_requirement
from evaluator import evaluate_prompt

req = load_requirement("input/requirement.md")
prompts = generate_all_prompts("input/requirement.md")
result = evaluate_prompt("test_case", prompts["test_case"], req)
print(result["generated_text"])
print("---")
print(result["scores"])
