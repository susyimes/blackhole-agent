import threading


class ConstructorRegistry(threading.local):
    def __init__(self, yaml_constructors_initialized=False, yaml_multi_constructors_initialized=False):
        self.yaml_constructors = {}
        self.yaml_multi_constructors = {}
        self.yaml_constructors_initialized = yaml_constructors_initialized
        self.yaml_multi_constructors_initialized = yaml_multi_constructors_initialized


class RepresenterRegistry(threading.local):
    def __init__(self, yaml_representers_initialized=False, yaml_multi_representers_initialized=False):
        self.yaml_representers = {}
        self.yaml_multi_representers = {}
        self.yaml_representers_initialized = yaml_representers_initialized
        self.yaml_multi_representers_initialized = yaml_multi_representers_initialized


class ResolverRegistry(threading.local):
    def __init__(self, yaml_implicit_resolvers_initialized=False, yaml_path_resolvers_initialized=False):
        self.yaml_implicit_resolvers = {}
        self.yaml_path_resolvers = {}
        self.yaml_implicit_resolvers_initialized = yaml_implicit_resolvers_initialized
        self.yaml_path_resolvers_initialized = yaml_path_resolvers_initialized


class RegistryMeta(type):
    """Metaclass to handle registry inheritance"""
    
    def __new__(cls, name, bases, attrs):
        cls = super().__new__(cls, name, bases, attrs)
        if 'constructor_registry' not in cls.__dict__:
            cls.constructor_registry = ConstructorRegistry()
        if 'representer_registry' not in cls.__dict__:
            cls.representer_registry = RepresenterRegistry()
        if 'resolver_registry' not in cls.__dict__:
            cls.resolver_registry = ResolverRegistry()
        return cls
