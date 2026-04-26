<!--
LinkedIn FEED POST, short-form social. Paste body below into the LinkedIn
"Start a post" composer. Upload writeup/thumbnail.png separately when
LinkedIn shows the image picker. ~1,800 chars; under the 3,000 hard limit.

Long-form companion (LinkedIn Pulse / Medium import): writeup/linkedin-article.md
-->

Why your eval harness needs a single-shot baseline

Most teams building LLM apps reach for an agent framework first. I benchmarked 8 popular ones against a 15-line single-shot script. The script kept winning.

Starting with a baseline isn't best-practice ceremony. It's the cheapest way to find out whether your fancy framework is buying anything.

The numbers

Same frozen model, same tasks, same grader. Tested: LangChain, LangGraph, CrewAI, and several smaller patterns from the literature.

Accuracy on messy HTML extraction: the single-shot baseline scored 9/15. The standard ReAct loop (the default in most agent tutorials) scored 2/15.

Speed: the baseline ran about 4x faster on wall-clock.

Cost: at frontier-model list prices, the baseline cost roughly 1/10th per task compared to the elaborate agent loops.

Three things I didn't expect

Hallucination at scale. A plan-and-execute agent fired the same non-existent CSS selector 417 times in a single run. The planner invented the selector. The executor had no way to tell the planner it didn't exist.

Variance even at temperature 0. Two runs of the same matrix produced middle-of-the-pack rankings that swung by 0.33 between the runs. seeds=1 evals are a coin flip.

On easy tasks the spread is all cost. For textbook algorithms with deterministic graders, every framework hit 15/15. The only differentiator was the bill: some test-driven patterns used 6x the input tokens to reach the same answer.

What to do with this

1. Add a 15-line single_shot baseline to your eval harness. Make it row zero of your results table.

2. If your production agent doesn't beat that baseline by more than 10%, simplify the stack. Latency and cost both drop.

3. Harness complexity pays returns only when first-shot accuracy is below target AND the failures are recoverable through extra turns. Both rarely hold at once on weak models.

None of this is anti-agent. It's pro-measurement: complexity should buy you something, and right now most of it isn't.

Full breakdown with charts and methodology:
🔗 https://jaafarbenabderrazak.com/blog/agent-frameworks-benchmark

Source code and reproducible 150-run matrix:
🔗 https://github.com/jaafar-benabderrazak/harness-bench

What's the simplest baseline you've never bothered to measure?

#SoftwareEngineering #LLMOps #AIArchitecture #AIBenchmarking #AgenticWorkflows
