import json
from websocietysimulator import Simulator
from websocietysimulator.agent import RecommendationAgent
import tiktoken
from websocietysimulator.llm import LLMBase, InfinigenceLLM
from websocietysimulator.agent.modules.planning_modules import PlanningBase
from websocietysimulator.agent.modules.reasoning_modules import ReasoningBase
import re
import logging
logging.basicConfig(level=logging.INFO)

def num_tokens_from_string(string: str) -> int:
    encoding = tiktoken.get_encoding("cl100k_base")
    return len(encoding.encode(string))

class RecPlanning(PlanningBase):
    """Inherits from PlanningBase"""
    
    def __init__(self, llm):
        """Initialize the planning module"""
        super().__init__(llm=llm)
    
    def create_prompt(self, task_type, task_description, feedback, few_shot):
        """Override the parent class's create_prompt method"""
        if feedback == '':
            prompt = '''You are a planner who divides a {task_type} task into several subtasks. You also need to give the reasoning instructions for each subtask. Your output format should follow the example below.
The following are some examples:
Task: I need to find some information to complete a recommendation task.
sub-task 1: {{"description": "First I need to find user information", "reasoning instruction": "None"}}
sub-task 2: {{"description": "Next, I need to find item information", "reasoning instruction": "None"}}
sub-task 3: {{"description": "Next, I need to find review information", "reasoning instruction": "None"}}

Task: {task_description}
'''
            prompt = prompt.format(task_description=task_description, task_type=task_type)
        else:
            prompt = '''You are a planner who divides a {task_type} task into several subtasks. You also need to give the reasoning instructions for each subtask. Your output format should follow the example below.
The following are some examples:
Task: I need to find some information to complete a recommendation task.
sub-task 1: {{"description": "First I need to find user information", "reasoning instruction": "None"}}
sub-task 2: {{"description": "Next, I need to find item information", "reasoning instruction": "None"}}
sub-task 3: {{"description": "Next, I need to find review information", "reasoning instruction": "None"}}

end
--------------------
Reflexion:{feedback}
Task:{task_description}
'''
            prompt = prompt.format(example=few_shot, task_description=task_description, task_type=task_type, feedback=feedback)
        return prompt

class RecReasoning(ReasoningBase):
    """Inherits from ReasoningBase"""
    
    def __init__(self, profile_type_prompt, llm):
        """Initialize the reasoning module"""
        super().__init__(profile_type_prompt=profile_type_prompt, memory=None, llm=llm)
        
    def __call__(self, task_description: str):
        """Override the parent class's __call__ method"""
        prompt = '''
{task_description}
Let's think step by step.
'''
        prompt = prompt.format(task_description=task_description)
        
        messages = [{"role": "user", "content": prompt}]
        reasoning_result = self.llm(
            messages=messages,
            temperature=0.1,
            max_tokens=1000
        )
        
        return reasoning_result

class MyRecommendationAgent(RecommendationAgent):
    """
    Participant's implementation of SimulationAgent
    """
    def __init__(self, llm:LLMBase):
        super().__init__(llm=llm)
        self.planning = RecPlanning(llm=self.llm)
        self.reasoning = RecReasoning(profile_type_prompt='', llm=self.llm)

    def workflow(self):
        """
        Simulate user behavior
        Returns:
            list: Sorted list of item IDs
        """
        plan = self.planning(task_type='Recommendation Task',
                             task_description="Please make a plan to query user information, you can choose to query user, item, and review information",
                             feedback='')
        print(f"The plan is :{plan}")

        user = ''
        item = []
        history_review = ''
        for sub_task in plan:
            
            if 'user' in sub_task['description']:
                user = str(self.interaction_tool.get_user(user_id=self.task['user_id']))
                input_tokens = num_tokens_from_string(user)
                if input_tokens > 21000:
                    encoding = tiktoken.get_encoding("cl100k_base")
                    user = encoding.decode(encoding.encode(user)[:21000])

            elif 'item' in sub_task['description']:
                for n_bus in range(len(self.task['candidate_list'])):
                    item.append(self.interaction_tool.get_item(item_id=self.task['candidate_list'][n_bus]))
                input_tokens = num_tokens_from_string(str(item))
                if input_tokens > 21000:
                    encoding = tiktoken.get_encoding("cl100k_base")
                    item = encoding.decode(encoding.encode(str(item))[:21000])

            elif 'review' in sub_task['description']:
                history_review = str(self.interaction_tool.get_reviews(user_id=self.task['user_id']))
                input_tokens = num_tokens_from_string(history_review)
                if input_tokens > 21000:
                    encoding = tiktoken.get_encoding("cl100k_base")
                    history_review = encoding.decode(encoding.encode(history_review)[:21000])
            else:
                pass
        task_description = f'''
        You are a user on Yelp with the profile: {user}. Your historical item review text and stars are as follows: {history_review}. The information of the above 20 candidate itemes is as follows: {item}.
        Now you need to rank the following 20 itemes: {self.task['candidate_list']} according to their match degree to your preference.
        Your output should be only a ranked item list without any other content:
        ['item id1', 'item id2', 'item id3', ...]
        '''
        result = self.reasoning(task_description)

        try:
            result = result.strip()
            match = re.search(r"\[.*\]", result, re.DOTALL)
            if match:
                result = match.group()
            else:
                print("No list found.")
        except:
            print('format error')
            result = self.task['candidate_list']

        print(f"The result is :{result}")
        return eval(result)

if __name__ == "__main__":
    task_set = "amazon" # "goodreads" or "yelp"
    # Initialize Simulator
    simulator = Simulator(data_dir="your data_dir", device="auto", cache=True)

    # Load scenarios
    simulator.set_task_and_groundtruth(task_dir=f"./track2/{task_set}/tasks", groundtruth_dir=f"./track2/{task_set}/groundtruth")

    # Set your custom agent
    simulator.set_agent(MyRecommendationAgent)

    # Set LLM client
    simulator.set_llm(InfinigenceLLM(api_key="your api_key"))

    # Run evaluation
    # If you don't set the number of tasks, the simulator will run all tasks.
    agent_outputs = simulator.run_simulation(number_of_tasks=None)

    # Evaluate the agent
    evaluation_results = simulator.evaluate()
    with open(f'./evaluation_results_track2_{task_set}.json', 'w') as f:
        json.dump(evaluation_results, f, indent=4)

    print(f"The evaluation_results is :{evaluation_results}")