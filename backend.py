import os 
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from typing import TypedDict, Literal
from pydantic import BaseModel, Field
from langgraph.graph import StateGraph, START, END
from fastapi import FastAPI, Request, Form
from fastapi.templating import Jinja2Templates

app = FastAPI(title="Multi-Agent Blog Writer-Dhanushka's Blog Writer", version="1.0")

templates = Jinja2Templates(directory="templates")



# Load environment variables from .env
load_dotenv()
model=os.getenv("MODEL")
max_revision=int(os.getenv("Max_Revision"))

print(f"Model: {model}")
print(f"Max Revision: {max_revision}")

#Define a model 

llm = ChatOpenAI(
    model=model,
    temperature=0,
)

print(f"Model: {llm.model_name}")


#Initiate the State memory, 
#To maintain memory of the conversation, we will use a list to store the messages
#TypeDict : Dictionary 
class AgentState(TypedDict): 
    topic: str
    draft: str
    feedback:str
    decision:str
    count:int

# Define Writer Agent
# Writes the first draft, or revises the draft using the reviewer's feedback
def writer_agent(state: AgentState) -> dict:
    if state.get("feedback"):
        print("\n--- Writer: Revising Draft ---")
        prompt = (
            f"You are a skilled writer. Revise the draft on the topic '{state['topic']}' "
            f"using the reviewer's feedback.\n\n"
            f"Draft:\n{state['draft']}\n\n"
            f"Feedback:\n{state['feedback']}\n\n"
            f"Return only the revised draft."
        )
    else:
        print("\n--- Writer: Creating Initial Draft ---")
        prompt = (
            f"You are a skilled writer. Write a clear, well-structured draft "
            f"on the topic: '{state['topic']}'.\n\n"
            f"Return only the draft."
        )

    response = llm.invoke(prompt)

    # Return only the fields that changed; LangGraph merges them into the state
    return {
        "draft": response.content,
        "count": state.get("count", 0) + 1,
    }


#test writer_agent
# topic =input("Enter the topic for the blog post: ")
# test_state = {"topic": topic, "count": 0}
# result = writer_agent(test_state)
# print(result)


#invoke the writer_agent using langgraph StateGraph
# Create the graph

# Create the graph
# def main():
#     builder = StateGraph(AgentState)

#     # Register your writer agent
#     builder.add_node("writer", writer_agent)

#     #reviewer calling 
#     builder.add_node("reviewer", reviewer_agent)

#     # Define the workflow
#     builder.add_edge(START, "writer")
#     builder.add_edge("writer", "reviewer")
#     #builder.add_edge("writer", END)
#     #call route_after_review to decide whether to go back to writer or end the workflow
#     builder.add_conditional_edges(
#     "reviewer",
#     route_after_review,
#     {
#         "writer": "writer",
#         "end": END,
#     },
#     )




#     # Compile the graph
#     graph = builder.compile()

#     # Execute the workflow
#     # initial_state: AgentState = {
#     #     "topic": "Benefits of AI in healthcare",
#     #     "draft": "",
#     #     "feedback": "",
#     #     "decision": "",
#     #     "count": 0,
#     # }
#     input_topic = input("Enter the topic for the blog post: ")
#     topic = input_topic.strip()  # Remove leading/trailing whitespace
#     result = graph.invoke({"topic": topic, "count": 0})

#     print("Generated draft:")
#     print(result["draft"])
#     print("Writer count:", result["count"])

#     print("reviewer result:")
    
#     print("Decision:", result.get("decision", "Missing from state"))
#     print("Feedback:", result.get("feedback", "Missing from state"))    
#     print("Full result:", result)
#     print("Available keys:", result.keys())



# create reviewer agent

# Reads the writer's draft, checks it against 6 quality criteria, and returns
# "decision" (PASS/FAIL) and "feedback" so route_after_review can end or loop back

#strict reviewing agent that provides feedback and a decision on the draft

def reviewer_agent(state: AgentState) -> dict:
    prompt = f"""
You are a STRICT and independent professional blog editor.
You must not approve a draft simply because it looks readable.

Topic: {state['topic']}

Draft:
{state['draft']}

Evaluate these criteria:
1. Relevance to the topic
2. Grammar and spelling
3. Clear introduction, body, and conclusion
4. Supporting examples or evidence
5. Logical structure and readability
6. Useful, accurate, sufficiently detailed content

Rules:
- PASS only if the draft meets ALL six criteria.
- FAIL if any important criterion is missing or weak.
- Identify specific problems in the actual draft.
- Do not invent problems that are not present.
- If FAIL, give actionable instructions for the writer.

Return exactly this format:

DECISION: PASS or FAIL
FEEDBACK: None or specific improvements

Do not include any other text.
"""

    response = llm.invoke(prompt)
    review = response.content.strip()

    print("\n--- Raw Reviewer Response ---")
    print(review)

    # Extract decision explicitly
    decision = "FAIL"

    for line in review.splitlines():
        if line.strip().upper() == "DECISION: PASS":
            decision = "PASS"
            break
        elif line.strip().upper() == "DECISION: FAIL":
            decision = "FAIL"
            break

    feedback = ""
    for line in review.splitlines():
        if line.strip().upper().startswith("FEEDBACK:"):
            feedback = line.split(":", 1)[1].strip()
            break

    if decision == "FAIL" and not feedback:
        feedback = "Provide a clearer, more complete and better-supported blog."

    print("\n--- Parsed Reviewer Result ---")
    print("Decision:", decision)
    print("Feedback:", feedback)

    return {
        "decision": decision,
        "feedback": feedback,
    }


def route_after_review(state: AgentState) -> Literal["writer", "end"]:
    if state["decision"] == "PASS":
        return "end"

    if state["count"] >= max_revision:
        return "end"
    
    return "writer"





# Build the LangGraph workflow
def build_graph():
    builder = StateGraph(AgentState)

    builder.add_node("writer", writer_agent)
    builder.add_node("reviewer", reviewer_agent)

    builder.add_edge(START, "writer")
    builder.add_edge("writer", "reviewer")

    builder.add_conditional_edges(
        "reviewer",
        route_after_review,
        {
            "writer": "writer",
            "end": END,
        },
    )

    return builder.compile()


# Create the graph once
graph = build_graph()


# Display the web page
@app.get("/")
async def home(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "topic": "",
            "draft": "",
            "decision": "",
            "feedback": "",
            "count": 0,
        },
    )


# Receive the topic and generate the blog
@app.post("/generate")
async def generate_blog(
    request: Request,
    topic: str = Form(...),
):
    topic = topic.strip()

    if not topic:
        return templates.TemplateResponse(
            request=request,
            name="index.html",
            context={
                "topic": "",
                "draft": "",
                "decision": "",
                "feedback": "",
                "count": 0,
                "error": "Please enter a topic.",
            },
        )

    initial_state: AgentState = {
        "topic": topic,
        "draft": "",
        "feedback": "",
        "decision": "",
        "count": 0,
    }

    # Run Writer -> Reviewer -> Revision loop
    result = graph.invoke(initial_state)

    # Display the final state in the browser
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "topic": topic,
            "draft": result["draft"],
            "draft": result["draft"],
            "decision": result["decision"],
            "feedback": result["feedback"],
            "count": result["count"],
        },
    )
# Route function decision marker for continuation of the workflow
