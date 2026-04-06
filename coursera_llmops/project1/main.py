#Adding auth and rate limiting to fastapi langchain workflows to ensure only authorized person can access.

# Secure fast api endpoints with JWT authentication and rate limiting using the `fastapi` library.

import os
from fastapi import FastAPI, Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel
from jose import JWTError, jwt #decoding and encoding JWT tokens
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from langchain_openai import AzureChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from datetime import datetime, timedelta
from dotenv import load_dotenv
import os
from langchain_core.output_parsers import StrOutputParser
from fastapi.responses import JSONResponse
load_dotenv()

api_key = os.getenv("AZURE_OPENAI_KEY")
api_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
api_version = os.getenv("AZURE_OPENAI_VERSION")

#JWT configuration
SECRET_KEY = os.getenv("SECRET_KEY")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30 #Token expiration time

def create_access_token(data:dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    print(to_encode)
    print(f"ENCODING SECRET KEY:{SECRET_KEY}")
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

oauth_scheme = OAuth2PasswordBearer(tokenUrl="token") #"Expect a token in request headers for protected endpoints, and the token can be obtained from the /token endpoint"
fake_user = {"username": "user1", "password": "password123"}

#add rate limiting to the app
app = FastAPI()
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

#auth endpoints
@app.post("/token")
def login(form_data: OAuth2PasswordRequestForm = Depends()):#gets the username and password from the form data
    if form_data.username != fake_user["username"] or form_data.password != fake_user["password"]:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    access_token = create_access_token(data={"sub": form_data.username})
    print(f"Access Token generated:{access_token}")
    return {"access_token": access_token, "token_type": "bearer"}


def get_current_user(token: str = Depends(oauth_scheme)):
    credentials_exception = HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Could not validate credentials")
    print(f"DECODING SECRET KEY:{SECRET_KEY}")
    print(f"TOKEN In Authorization:{token}")
    try:
        print("Decoding payload")
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        print(f"Decoded payload:{payload}")
        username: str = payload.get("sub")
        if username is None:
            print("Username is none!")
            raise credentials_exception
    except JWTError:
        print("JWT Token error")
        raise credentials_exception
    return username

#create a langchain workflow
prompt = ChatPromptTemplate.from_messages(
    [
        ("system", "You are an assistant that answers in a concise manner. Keep your answers short and to the point."),
        ("human","{question}")
    ])
llm = AzureChatOpenAI(
    azure_endpoint= api_endpoint,
    azure_deployment= "gpt-4o-mini",
    openai_api_key=api_key,
    openai_api_version=api_version,
    temperature = 0.7,)
chain = prompt | llm | StrOutputParser()

def run_workflow(question: str):
    response =  chain.invoke({"question": question})
    print(response)
    return response

class Question(BaseModel):
    question: str

@app.post("/ask")
@limiter.limit("5/minute") #limit to 5 requests per minute
async def ask_question(request: Request,
question: Question, current_user: str = Depends(get_current_user)):
    print(f"Received question:",question)
    response = run_workflow(question.question)
    print(f"Received response:{response}")
    return JSONResponse(
        content={"question": question.question, "answer": response}
    )

@app.get("/")
async def landing_page():
    return {"message": "Welcome to the LangChain Workflow API. Please authenticate using /token to get a JWT and use it to access the /ask endpoint."}


#Lets a user login → gets a JWT token(if the username and password are correct) → user can then use that token to access the /ask endpoint where they can ask a question to the LLM. The system will rate limit the number of questions a user can ask to 5 per minute.
# Uses that token to access a protected API
# Calls an LLM (LangChain + Azure OpenAI)
# Limits how many times user can call it (rate limiting)

#flow 
#POST /token http://localhost:8000/token
#username + password -> JWT token
#POST /ask
#Authorization: Bearer <JWT token>
#question -> LLM response
# Client → /ask request
#         ↓
# FastAPI sees Depends(get_current_user)
#         ↓
# Calls oauth_scheme → extracts token
#         ↓
# Calls get_current_user(token)
#         ↓
# jwt.decode() validates token
#         ↓
# If valid → continue
# If invalid → 401 error
#         ↓
# ask_question() executes


# To test:
# 1. Start the server: `uvicorn c8_jwt_oauth:app --reload`
# 2. Get a token via POST request to /token with form data: username=user1, password=password123, copy the token from the response
# 3. Use the token to access /ask endpoint with a question in the body, and include the token in the Authorization header as: Bearer <token>
#In the authorization header, the format is "Bearer"