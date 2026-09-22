If deemed a better solution, create it as an n8n implementation instead of systemd.
Feel free to install any tools that can make this multi agent setup better.
The LiteLLM stuff is for a smaller hardware platform, the LLM is maximum a qwen3.5:9b model, so keep AI tasks short and simple.
I want to divide this monolith. I want one flow to handle apt packages, one to handle manually installed software, on to handle docker, one to handle python pip packages. Feel free to expand if needed. It can still be in one change.
Create a document or drawing that shows how this design is, if n8n is not chosen as a solution. I need a good way to understand the flow from start to finish.

