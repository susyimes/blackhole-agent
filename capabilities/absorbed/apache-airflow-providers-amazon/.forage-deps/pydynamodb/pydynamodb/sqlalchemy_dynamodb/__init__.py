from sqlalchemy.dialects import registry

registry.register(
    "dynamodb", "pydynamodb.sqlalchemy_dynamodb.pydynamodb", "DynamoDBDialect"
)
registry.register(
    "dynamodb.rest", "pydynamodb.sqlalchemy_dynamodb.pydynamodb", "DynamoDBRestDialect"
)
