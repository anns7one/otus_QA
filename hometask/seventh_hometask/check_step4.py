import sys
sys.stdout.reconfigure(encoding="utf-8")

from prompt_generator import generate_all_prompts, load_requirement
from evaluator import evaluate_prompt

req = load_requirement("requirement.md")
prompts = generate_all_prompts("requirement.md")
result = evaluate_prompt("test_case", prompts["test_case"], req)
print(result["generated_text"])
print("---")
print(result["scores"])
