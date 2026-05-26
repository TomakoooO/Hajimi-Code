---
name: plantuml-sequence-diagram
description: Create professional sequence diagrams using PlantUML syntax. Use when user asks to draw sequence diagrams, system interactions, API flows, process workflows, or multi-agent collaboration steps.
---

# PlantUML Sequence Diagram Skill

You now have expertise in creating professional, syntactically correct sequence diagrams using PlantUML. Follow these workflows to generate clean, readable diagrams that can be rendered in any PlantUML-compatible tool.

## Basic Sequence Diagrams

**Option 1: Simple 3-party interaction (most common)**
```plantuml
@startuml Simple Interaction
actor User
participant "Frontend App" as Frontend
participant "Backend API" as Backend

User -> Frontend: Clicks "Submit" button
Frontend -> Backend: POST /api/data
Backend --> Frontend: 200 OK {success: true}
Frontend --> User: Shows success message
@enduml
```

**Option 2: With activation bars (show object lifecycle)**
```plantuml
@startuml With Activation
actor User
participant Frontend
participant Backend
database Database

User -> Frontend: Request data
activate Frontend
Frontend -> Backend: GET /api/users
activate Backend
Backend -> Database: SELECT * FROM users
activate Database
Database --> Backend: Returns user list
deactivate Database
Backend --> Frontend: 200 OK [users]
deactivate Backend
Frontend --> User: Displays user table
deactivate Frontend
@enduml
```

## Advanced Sequence Diagrams

**Option 1: Conditional logic (alt/else)**
```plantuml
@startuml Conditional Logic
actor User
participant AuthService
participant UserService

User -> AuthService: Login(username, password)
activate AuthService
AuthService -> UserService: Verify credentials
activate UserService

alt Credentials valid
    UserService --> AuthService: User authenticated
    AuthService --> User: Returns JWT token
else Credentials invalid
    UserService --> AuthService: Authentication failed
    AuthService --> User: 401 Unauthorized
end

deactivate UserService
deactivate AuthService
@enduml
```

**Option 2: Loops (repeat operations)**
```plantuml
@startuml Loop Example
participant BatchProcessor
database Database

BatchProcessor -> Database: Get pending jobs
Database --> BatchProcessor: [Job1, Job2, Job3]

loop For each job in list
    BatchProcessor -> BatchProcessor: Process job
    BatchProcessor -> Database: Update job status
end

BatchProcessor --> BatchProcessor: Send completion notification
@enduml
```

**Option 3: Asynchronous calls & callbacks**
```plantuml
@startuml Asynchronous Calls
participant Client
participant MessageQueue
participant Worker

Client ->> MessageQueue: Publish task (async)
Client --> Client: Continue other work

MessageQueue ->> Worker: Deliver task
activate Worker
Worker -> Worker: Process long-running task
Worker -->> Client: Task completed (callback)
deactivate Worker
@enduml
```

## Common Patterns

**Option 1: Error handling with exceptions**
```plantuml
@startuml Error Handling
participant OrderService
participant PaymentService
participant InventoryService

OrderService -> PaymentService: Process payment($100)
activate PaymentService

try
    PaymentService -> InventoryService: Check stock
    InventoryService --> PaymentService: Stock available
    PaymentService --> OrderService: Payment successful
catch PaymentFailed
    PaymentService --> OrderService: Payment failed - insufficient funds
catch OutOfStock
    PaymentService --> OrderService: Payment failed - item out of stock
end

deactivate PaymentService
@enduml
```

**Option 2: Database transaction flow**
```plantuml
@startuml Database Transaction
participant Service
database DB

Service -> DB: BEGIN TRANSACTION
activate DB
Service -> DB: INSERT INTO orders (...)
Service -> DB: UPDATE inventory SET stock=stock-1
Service -> DB: COMMIT
deactivate DB
Service --> Service: Transaction completed
@enduml
```

**Option 3: Multi-agent collaboration flow**
```plantuml
@startuml Agent Collaboration
actor User
participant "Orchestrator Agent" as Orchestrator
participant "Search Agent" as Search
participant "Analysis Agent" as Analysis
participant "Report Agent" as Report

User -> Orchestrator: "Analyze market trends for AI chips"
Orchestrator -> Search: Search latest AI chip news
Search --> Orchestrator: Returns 50 relevant articles
Orchestrator -> Analysis: Analyze articles for trends
Analysis --> Orchestrator: Returns trend summary
Orchestrator -> Report: Generate final report
Report --> Orchestrator: Returns formatted report
Orchestrator --> User: Presents market analysis report
@enduml
```

## Styling & Customization

**Option 1: Minimal clean style (recommended for documentation)**
```plantuml
@startuml Clean Style
skinparam sequence {
    ArrowColor #2c3e50
    ActorBorderColor #34495e
    ParticipantBorderColor #34495e
    ParticipantBackgroundColor #ecf0f1
    ActorBackgroundColor #ecf0f1
    LifeLineBorderColor #bdc3c7
    LifeLineBackgroundColor #ffffff
    NoteBackgroundColor #f8f9fa
    NoteBorderColor #dee2e6
}

actor User
participant Frontend
participant Backend

User -> Frontend: Request
Frontend -> Backend: API Call
Backend --> Frontend: Response
Frontend --> User: Result
@enduml
```

**Option 2: Color-coded participants for better readability**
```plantuml
@startuml Color Coded
actor User #3498db
participant "Frontend App" #2ecc71
participant "Backend API" #f39c12
database "Database" #9b59b6
boundary "Third-Party API" #e74c3c

User -> Frontend: Request
Frontend -> Backend: API Call
Backend -> Database: Query
Database --> Backend: Data
Backend -> "Third-Party API": External request
"Third-Party API" --> Backend: External response
Backend --> Frontend: Response
Frontend --> User: Result
@enduml
```

## Key Tools & Renderers

| Tool/Platform | Use Case | How to Access |
|---------------|----------|---------------|
| PlantUML Online Editor | Quick testing and rendering | https://www.plantuml.com/plantuml/ |
| VSCode PlantUML Extension | Local development with live preview | Install from VSCode Marketplace |
| IntelliJ PlantUML Plugin | JetBrains IDE integration | Install from JetBrains Marketplace |
| Markdown Renderers | Embed diagrams in Markdown | GitHub, GitLab, Obsidian, MkDocs |
| Pandoc | Generate diagrams in PDF/Word documents | `pandoc --filter pandoc-plantuml` |

## Best Practices

1. **Keep diagrams focused**: Limit to 5-7 participants and 15-20 interactions per diagram. Split complex flows into multiple smaller diagrams.
2. **Use meaningful names**: Name participants and messages clearly, avoid abbreviations unless they are universally understood.
3. **Use correct arrow types**: `->` for synchronous calls, `-->` for synchronous returns, `->>` for asynchronous calls, `-->>` for asynchronous callbacks.
4. **Show object lifecycle**: Use `activate` and `deactivate` to indicate when objects are processing requests.
5. **Group related logic**: Use `alt` (conditions), `loop` (repetition), `opt` (optional steps), and `par` (parallel execution) blocks to organize complex flows.
6. **Add notes sparingly**: Use `note left of`, `note right of`, or `note over` to explain complex parts without cluttering the diagram.
7. **Test your code**: Always verify that your PlantUML code renders correctly in a compatible tool before sharing.
8. **Follow consistent styling**: Use a consistent color scheme and formatting across all diagrams in a project.

需要我帮你把这个技能文档转换成**可直接复制到Word的标准格式**，或者添加一个**完整的微服务调用链路示例**吗？