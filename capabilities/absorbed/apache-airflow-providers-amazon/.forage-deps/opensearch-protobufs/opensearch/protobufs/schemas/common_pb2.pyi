from google.protobuf import descriptor_pb2 as _descriptor_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Iterable as _Iterable, Mapping as _Mapping, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class FieldValueFactorModifier(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    FIELD_VALUE_FACTOR_MODIFIER_UNSPECIFIED: _ClassVar[FieldValueFactorModifier]
    FIELD_VALUE_FACTOR_MODIFIER_LN: _ClassVar[FieldValueFactorModifier]
    FIELD_VALUE_FACTOR_MODIFIER_LN1P: _ClassVar[FieldValueFactorModifier]
    FIELD_VALUE_FACTOR_MODIFIER_LN2P: _ClassVar[FieldValueFactorModifier]
    FIELD_VALUE_FACTOR_MODIFIER_LOG: _ClassVar[FieldValueFactorModifier]
    FIELD_VALUE_FACTOR_MODIFIER_LOG1P: _ClassVar[FieldValueFactorModifier]
    FIELD_VALUE_FACTOR_MODIFIER_LOG2P: _ClassVar[FieldValueFactorModifier]
    FIELD_VALUE_FACTOR_MODIFIER_NONE: _ClassVar[FieldValueFactorModifier]
    FIELD_VALUE_FACTOR_MODIFIER_RECIPROCAL: _ClassVar[FieldValueFactorModifier]
    FIELD_VALUE_FACTOR_MODIFIER_SQRT: _ClassVar[FieldValueFactorModifier]
    FIELD_VALUE_FACTOR_MODIFIER_SQUARE: _ClassVar[FieldValueFactorModifier]

class WaitForActiveShardOptions(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    WAIT_FOR_ACTIVE_SHARD_OPTIONS_UNSPECIFIED: _ClassVar[WaitForActiveShardOptions]
    WAIT_FOR_ACTIVE_SHARD_OPTIONS_ALL: _ClassVar[WaitForActiveShardOptions]
    WAIT_FOR_ACTIVE_SHARD_OPTIONS_NULL: _ClassVar[WaitForActiveShardOptions]

class TotalHitsRelation(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    TOTAL_HITS_RELATION_UNSPECIFIED: _ClassVar[TotalHitsRelation]
    TOTAL_HITS_RELATION_EQ: _ClassVar[TotalHitsRelation]
    TOTAL_HITS_RELATION_GTE: _ClassVar[TotalHitsRelation]

class ScoreMode(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    SCORE_MODE_UNSPECIFIED: _ClassVar[ScoreMode]
    SCORE_MODE_AVG: _ClassVar[ScoreMode]
    SCORE_MODE_MAX: _ClassVar[ScoreMode]
    SCORE_MODE_MIN: _ClassVar[ScoreMode]
    SCORE_MODE_MULTIPLY: _ClassVar[ScoreMode]
    SCORE_MODE_TOTAL: _ClassVar[ScoreMode]

class OpType(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    OP_TYPE_UNSPECIFIED: _ClassVar[OpType]
    OP_TYPE_CREATE: _ClassVar[OpType]
    OP_TYPE_INDEX: _ClassVar[OpType]

class VersionType(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    VERSION_TYPE_UNSPECIFIED: _ClassVar[VersionType]
    VERSION_TYPE_EXTERNAL: _ClassVar[VersionType]
    VERSION_TYPE_EXTERNAL_GTE: _ClassVar[VersionType]
    VERSION_TYPE_INTERNAL: _ClassVar[VersionType]
    VERSION_TYPE_FORCE: _ClassVar[VersionType]

class Refresh(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    REFRESH_UNSPECIFIED: _ClassVar[Refresh]
    REFRESH_FALSE: _ClassVar[Refresh]
    REFRESH_TRUE: _ClassVar[Refresh]
    REFRESH_WAIT_FOR: _ClassVar[Refresh]

class BuiltinScriptLanguage(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    BUILTIN_SCRIPT_LANGUAGE_UNSPECIFIED: _ClassVar[BuiltinScriptLanguage]
    BUILTIN_SCRIPT_LANGUAGE_EXPRESSION: _ClassVar[BuiltinScriptLanguage]
    BUILTIN_SCRIPT_LANGUAGE_JAVA: _ClassVar[BuiltinScriptLanguage]
    BUILTIN_SCRIPT_LANGUAGE_MUSTACHE: _ClassVar[BuiltinScriptLanguage]
    BUILTIN_SCRIPT_LANGUAGE_PAINLESS: _ClassVar[BuiltinScriptLanguage]

class ExpandWildcard(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    EXPAND_WILDCARD_UNSPECIFIED: _ClassVar[ExpandWildcard]
    EXPAND_WILDCARD_ALL: _ClassVar[ExpandWildcard]
    EXPAND_WILDCARD_CLOSED: _ClassVar[ExpandWildcard]
    EXPAND_WILDCARD_HIDDEN: _ClassVar[ExpandWildcard]
    EXPAND_WILDCARD_NONE: _ClassVar[ExpandWildcard]
    EXPAND_WILDCARD_OPEN: _ClassVar[ExpandWildcard]

class SearchType(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    SEARCH_TYPE_UNSPECIFIED: _ClassVar[SearchType]
    SEARCH_TYPE_DFS_QUERY_THEN_FETCH: _ClassVar[SearchType]
    SEARCH_TYPE_QUERY_THEN_FETCH: _ClassVar[SearchType]

class SuggestMode(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    SUGGEST_MODE_UNSPECIFIED: _ClassVar[SuggestMode]
    SUGGEST_MODE_ALWAYS: _ClassVar[SuggestMode]
    SUGGEST_MODE_MISSING: _ClassVar[SuggestMode]
    SUGGEST_MODE_POPULAR: _ClassVar[SuggestMode]

class RangeRelation(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    RANGE_RELATION_UNSPECIFIED: _ClassVar[RangeRelation]
    RANGE_RELATION_CONTAINS: _ClassVar[RangeRelation]
    RANGE_RELATION_INTERSECTS: _ClassVar[RangeRelation]
    RANGE_RELATION_WITHIN: _ClassVar[RangeRelation]

class TextQueryType(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    TEXT_QUERY_TYPE_UNSPECIFIED: _ClassVar[TextQueryType]
    TEXT_QUERY_TYPE_BEST_FIELDS: _ClassVar[TextQueryType]
    TEXT_QUERY_TYPE_BOOL_PREFIX: _ClassVar[TextQueryType]
    TEXT_QUERY_TYPE_CROSS_FIELDS: _ClassVar[TextQueryType]
    TEXT_QUERY_TYPE_MOST_FIELDS: _ClassVar[TextQueryType]
    TEXT_QUERY_TYPE_PHRASE: _ClassVar[TextQueryType]
    TEXT_QUERY_TYPE_PHRASE_PREFIX: _ClassVar[TextQueryType]

class ZeroTermsQuery(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    ZERO_TERMS_QUERY_UNSPECIFIED: _ClassVar[ZeroTermsQuery]
    ZERO_TERMS_QUERY_ALL: _ClassVar[ZeroTermsQuery]
    ZERO_TERMS_QUERY_NONE: _ClassVar[ZeroTermsQuery]

class TermsQueryValueType(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    TERMS_QUERY_VALUE_TYPE_UNSPECIFIED: _ClassVar[TermsQueryValueType]
    TERMS_QUERY_VALUE_TYPE_BITMAP: _ClassVar[TermsQueryValueType]
    TERMS_QUERY_VALUE_TYPE_DEFAULT: _ClassVar[TermsQueryValueType]

class MultiValueMode(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    MULTI_VALUE_MODE_UNSPECIFIED: _ClassVar[MultiValueMode]
    MULTI_VALUE_MODE_AVG: _ClassVar[MultiValueMode]
    MULTI_VALUE_MODE_MAX: _ClassVar[MultiValueMode]
    MULTI_VALUE_MODE_MIN: _ClassVar[MultiValueMode]
    MULTI_VALUE_MODE_SUM: _ClassVar[MultiValueMode]

class FunctionBoostMode(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    FUNCTION_BOOST_MODE_UNSPECIFIED: _ClassVar[FunctionBoostMode]
    FUNCTION_BOOST_MODE_AVG: _ClassVar[FunctionBoostMode]
    FUNCTION_BOOST_MODE_MAX: _ClassVar[FunctionBoostMode]
    FUNCTION_BOOST_MODE_MIN: _ClassVar[FunctionBoostMode]
    FUNCTION_BOOST_MODE_MULTIPLY: _ClassVar[FunctionBoostMode]
    FUNCTION_BOOST_MODE_REPLACE: _ClassVar[FunctionBoostMode]
    FUNCTION_BOOST_MODE_SUM: _ClassVar[FunctionBoostMode]

class FunctionScoreMode(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    FUNCTION_SCORE_MODE_UNSPECIFIED: _ClassVar[FunctionScoreMode]
    FUNCTION_SCORE_MODE_AVG: _ClassVar[FunctionScoreMode]
    FUNCTION_SCORE_MODE_FIRST: _ClassVar[FunctionScoreMode]
    FUNCTION_SCORE_MODE_MAX: _ClassVar[FunctionScoreMode]
    FUNCTION_SCORE_MODE_MIN: _ClassVar[FunctionScoreMode]
    FUNCTION_SCORE_MODE_MULTIPLY: _ClassVar[FunctionScoreMode]
    FUNCTION_SCORE_MODE_SUM: _ClassVar[FunctionScoreMode]

class Operator(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    OPERATOR_UNSPECIFIED: _ClassVar[Operator]
    OPERATOR_AND: _ClassVar[Operator]
    OPERATOR_OR: _ClassVar[Operator]

class MultiTermQueryRewrite(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    MULTI_TERM_QUERY_REWRITE_UNSPECIFIED: _ClassVar[MultiTermQueryRewrite]
    MULTI_TERM_QUERY_REWRITE_CONSTANT_SCORE: _ClassVar[MultiTermQueryRewrite]
    MULTI_TERM_QUERY_REWRITE_CONSTANT_SCORE_BOOLEAN: _ClassVar[MultiTermQueryRewrite]
    MULTI_TERM_QUERY_REWRITE_SCORING_BOOLEAN: _ClassVar[MultiTermQueryRewrite]
    MULTI_TERM_QUERY_REWRITE_TOP_TERMS_N: _ClassVar[MultiTermQueryRewrite]
    MULTI_TERM_QUERY_REWRITE_TOP_TERMS_BLENDED_FREQS_N: _ClassVar[MultiTermQueryRewrite]
    MULTI_TERM_QUERY_REWRITE_TOP_TERMS_BOOST_N: _ClassVar[MultiTermQueryRewrite]

class GeoValidationMethod(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    GEO_VALIDATION_METHOD_UNSPECIFIED: _ClassVar[GeoValidationMethod]
    GEO_VALIDATION_METHOD_COERCE: _ClassVar[GeoValidationMethod]
    GEO_VALIDATION_METHOD_IGNORE_MALFORMED: _ClassVar[GeoValidationMethod]
    GEO_VALIDATION_METHOD_STRICT: _ClassVar[GeoValidationMethod]

class ScriptSortType(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    SCRIPT_SORT_TYPE_UNSPECIFIED: _ClassVar[ScriptSortType]
    SCRIPT_SORT_TYPE_NUMBER: _ClassVar[ScriptSortType]
    SCRIPT_SORT_TYPE_STRING: _ClassVar[ScriptSortType]
    SCRIPT_SORT_TYPE_VERSION: _ClassVar[ScriptSortType]

class FieldSortNumericType(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    FIELD_SORT_NUMERIC_TYPE_UNSPECIFIED: _ClassVar[FieldSortNumericType]
    FIELD_SORT_NUMERIC_TYPE_DATE: _ClassVar[FieldSortNumericType]
    FIELD_SORT_NUMERIC_TYPE_DATE_NANOS: _ClassVar[FieldSortNumericType]
    FIELD_SORT_NUMERIC_TYPE_DOUBLE: _ClassVar[FieldSortNumericType]
    FIELD_SORT_NUMERIC_TYPE_LONG: _ClassVar[FieldSortNumericType]

class FieldType(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    FIELD_TYPE_UNSPECIFIED: _ClassVar[FieldType]
    FIELD_TYPE_AGGREGATE_METRIC_DOUBLE: _ClassVar[FieldType]
    FIELD_TYPE_ALIAS: _ClassVar[FieldType]
    FIELD_TYPE_BINARY: _ClassVar[FieldType]
    FIELD_TYPE_BOOLEAN: _ClassVar[FieldType]
    FIELD_TYPE_BYTE: _ClassVar[FieldType]
    FIELD_TYPE_COMPLETION: _ClassVar[FieldType]
    FIELD_TYPE_CONSTANT_KEYWORD: _ClassVar[FieldType]
    FIELD_TYPE_DATE: _ClassVar[FieldType]
    FIELD_TYPE_DATE_NANOS: _ClassVar[FieldType]
    FIELD_TYPE_DATE_RANGE: _ClassVar[FieldType]
    FIELD_TYPE_DOUBLE: _ClassVar[FieldType]
    FIELD_TYPE_DOUBLE_RANGE: _ClassVar[FieldType]
    FIELD_TYPE_FLAT_OBJECT: _ClassVar[FieldType]
    FIELD_TYPE_FLOAT: _ClassVar[FieldType]
    FIELD_TYPE_FLOAT_RANGE: _ClassVar[FieldType]
    FIELD_TYPE_GEO_POINT: _ClassVar[FieldType]
    FIELD_TYPE_GEO_SHAPE: _ClassVar[FieldType]
    FIELD_TYPE_HALF_FLOAT: _ClassVar[FieldType]
    FIELD_TYPE_HISTOGRAM: _ClassVar[FieldType]
    FIELD_TYPE_ICU_COLLATION_KEYWORD: _ClassVar[FieldType]
    FIELD_TYPE_INTEGER: _ClassVar[FieldType]
    FIELD_TYPE_INTEGER_RANGE: _ClassVar[FieldType]
    FIELD_TYPE_IP: _ClassVar[FieldType]
    FIELD_TYPE_IP_RANGE: _ClassVar[FieldType]
    FIELD_TYPE_JOIN: _ClassVar[FieldType]
    FIELD_TYPE_KEYWORD: _ClassVar[FieldType]
    FIELD_TYPE_KNN_VECTOR: _ClassVar[FieldType]
    FIELD_TYPE_LONG: _ClassVar[FieldType]
    FIELD_TYPE_LONG_RANGE: _ClassVar[FieldType]
    FIELD_TYPE_MATCH_ONLY_TEXT: _ClassVar[FieldType]
    FIELD_TYPE_MURMUR3: _ClassVar[FieldType]
    FIELD_TYPE_NESTED: _ClassVar[FieldType]
    FIELD_TYPE_OBJECT: _ClassVar[FieldType]
    FIELD_TYPE_PERCOLATOR: _ClassVar[FieldType]
    FIELD_TYPE_RANK_FEATURE: _ClassVar[FieldType]
    FIELD_TYPE_RANK_FEATURES: _ClassVar[FieldType]
    FIELD_TYPE_SCALED_FLOAT: _ClassVar[FieldType]
    FIELD_TYPE_SEARCH_AS_YOU_TYPE: _ClassVar[FieldType]
    FIELD_TYPE_SHORT: _ClassVar[FieldType]
    FIELD_TYPE_TEXT: _ClassVar[FieldType]
    FIELD_TYPE_TOKEN_COUNT: _ClassVar[FieldType]
    FIELD_TYPE_UNSIGNED_LONG: _ClassVar[FieldType]
    FIELD_TYPE_VERSION: _ClassVar[FieldType]
    FIELD_TYPE_WILDCARD: _ClassVar[FieldType]
    FIELD_TYPE_XY_POINT: _ClassVar[FieldType]
    FIELD_TYPE_XY_SHAPE: _ClassVar[FieldType]
    FIELD_TYPE_SEMANTIC: _ClassVar[FieldType]

class SortOrder(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    SORT_ORDER_UNSPECIFIED: _ClassVar[SortOrder]
    SORT_ORDER_ASC: _ClassVar[SortOrder]
    SORT_ORDER_DESC: _ClassVar[SortOrder]

class SortMode(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    SORT_MODE_UNSPECIFIED: _ClassVar[SortMode]
    SORT_MODE_AVG: _ClassVar[SortMode]
    SORT_MODE_MAX: _ClassVar[SortMode]
    SORT_MODE_MEDIAN: _ClassVar[SortMode]
    SORT_MODE_MIN: _ClassVar[SortMode]
    SORT_MODE_SUM: _ClassVar[SortMode]

class GeoDistanceType(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    GEO_DISTANCE_TYPE_UNSPECIFIED: _ClassVar[GeoDistanceType]
    GEO_DISTANCE_TYPE_ARC: _ClassVar[GeoDistanceType]
    GEO_DISTANCE_TYPE_PLANE: _ClassVar[GeoDistanceType]

class BuiltinHighlighterType(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    BUILTIN_HIGHLIGHTER_TYPE_UNSPECIFIED: _ClassVar[BuiltinHighlighterType]
    BUILTIN_HIGHLIGHTER_TYPE_PLAIN: _ClassVar[BuiltinHighlighterType]
    BUILTIN_HIGHLIGHTER_TYPE_FVH: _ClassVar[BuiltinHighlighterType]
    BUILTIN_HIGHLIGHTER_TYPE_UNIFIED: _ClassVar[BuiltinHighlighterType]

class BoundaryScanner(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    BOUNDARY_SCANNER_UNSPECIFIED: _ClassVar[BoundaryScanner]
    BOUNDARY_SCANNER_CHARS: _ClassVar[BoundaryScanner]
    BOUNDARY_SCANNER_SENTENCE: _ClassVar[BoundaryScanner]
    BOUNDARY_SCANNER_WORD: _ClassVar[BoundaryScanner]

class HighlighterFragmenter(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    HIGHLIGHTER_FRAGMENTER_UNSPECIFIED: _ClassVar[HighlighterFragmenter]
    HIGHLIGHTER_FRAGMENTER_SIMPLE: _ClassVar[HighlighterFragmenter]
    HIGHLIGHTER_FRAGMENTER_SPAN: _ClassVar[HighlighterFragmenter]

class HighlighterOrder(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    HIGHLIGHTER_ORDER_UNSPECIFIED: _ClassVar[HighlighterOrder]
    HIGHLIGHTER_ORDER_SCORE: _ClassVar[HighlighterOrder]

class HighlighterTagsSchema(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    HIGHLIGHTER_TAGS_SCHEMA_UNSPECIFIED: _ClassVar[HighlighterTagsSchema]
    HIGHLIGHTER_TAGS_SCHEMA_STYLED: _ClassVar[HighlighterTagsSchema]
    HIGHLIGHTER_TAGS_SCHEMA_DEFAULT: _ClassVar[HighlighterTagsSchema]

class DistanceUnit(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    DISTANCE_UNIT_UNSPECIFIED: _ClassVar[DistanceUnit]
    DISTANCE_UNIT_CM: _ClassVar[DistanceUnit]
    DISTANCE_UNIT_FT: _ClassVar[DistanceUnit]
    DISTANCE_UNIT_IN: _ClassVar[DistanceUnit]
    DISTANCE_UNIT_KM: _ClassVar[DistanceUnit]
    DISTANCE_UNIT_M: _ClassVar[DistanceUnit]
    DISTANCE_UNIT_MI: _ClassVar[DistanceUnit]
    DISTANCE_UNIT_MM: _ClassVar[DistanceUnit]
    DISTANCE_UNIT_NMI: _ClassVar[DistanceUnit]
    DISTANCE_UNIT_YD: _ClassVar[DistanceUnit]

class ChildScoreMode(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    CHILD_SCORE_MODE_UNSPECIFIED: _ClassVar[ChildScoreMode]
    CHILD_SCORE_MODE_AVG: _ClassVar[ChildScoreMode]
    CHILD_SCORE_MODE_MAX: _ClassVar[ChildScoreMode]
    CHILD_SCORE_MODE_MIN: _ClassVar[ChildScoreMode]
    CHILD_SCORE_MODE_NONE: _ClassVar[ChildScoreMode]
    CHILD_SCORE_MODE_SUM: _ClassVar[ChildScoreMode]

class HighlighterEncoder(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    HIGHLIGHTER_ENCODER_UNSPECIFIED: _ClassVar[HighlighterEncoder]
    HIGHLIGHTER_ENCODER_DEFAULT: _ClassVar[HighlighterEncoder]
    HIGHLIGHTER_ENCODER_HTML: _ClassVar[HighlighterEncoder]

class GeoExecution(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    GEO_EXECUTION_UNSPECIFIED: _ClassVar[GeoExecution]
    GEO_EXECUTION_INDEXED: _ClassVar[GeoExecution]
    GEO_EXECUTION_MEMORY: _ClassVar[GeoExecution]

class TermsAggregationCollectMode(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    TERMS_AGGREGATION_COLLECT_MODE_UNSPECIFIED: _ClassVar[TermsAggregationCollectMode]
    TERMS_AGGREGATION_COLLECT_MODE_BREADTH_FIRST: _ClassVar[TermsAggregationCollectMode]
    TERMS_AGGREGATION_COLLECT_MODE_DEPTH_FIRST: _ClassVar[TermsAggregationCollectMode]

class TermsAggregationExecutionHint(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    TERMS_AGGREGATION_EXECUTION_HINT_UNSPECIFIED: _ClassVar[TermsAggregationExecutionHint]
    TERMS_AGGREGATION_EXECUTION_HINT_GLOBAL_ORDINALS: _ClassVar[TermsAggregationExecutionHint]
    TERMS_AGGREGATION_EXECUTION_HINT_GLOBAL_ORDINALS_HASH: _ClassVar[TermsAggregationExecutionHint]
    TERMS_AGGREGATION_EXECUTION_HINT_GLOBAL_ORDINALS_LOW_CARDINALITY: _ClassVar[TermsAggregationExecutionHint]
    TERMS_AGGREGATION_EXECUTION_HINT_MAP: _ClassVar[TermsAggregationExecutionHint]

class ValueType(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    VALUE_TYPE_UNSPECIFIED: _ClassVar[ValueType]
    VALUE_TYPE_BOOLEAN: _ClassVar[ValueType]
    VALUE_TYPE_BYTE: _ClassVar[ValueType]
    VALUE_TYPE_DATE: _ClassVar[ValueType]
    VALUE_TYPE_DOUBLE: _ClassVar[ValueType]
    VALUE_TYPE_FLOAT: _ClassVar[ValueType]
    VALUE_TYPE_INTEGER: _ClassVar[ValueType]
    VALUE_TYPE_IP: _ClassVar[ValueType]
    VALUE_TYPE_LONG: _ClassVar[ValueType]
    VALUE_TYPE_NUMBER: _ClassVar[ValueType]
    VALUE_TYPE_NUMERIC: _ClassVar[ValueType]
    VALUE_TYPE_SHORT: _ClassVar[ValueType]
    VALUE_TYPE_STRING: _ClassVar[ValueType]
    VALUE_TYPE_UNSIGNED_LONG: _ClassVar[ValueType]

class ByteOrder(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    BYTE_ORDER_UNSPECIFIED: _ClassVar[ByteOrder]
    BYTE_ORDER_BIG_ENDIAN: _ClassVar[ByteOrder]
    BYTE_ORDER_LITTLE_ENDIAN: _ClassVar[ByteOrder]

class ColumnType(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    COLUMN_TYPE_UNSPECIFIED: _ClassVar[ColumnType]
    COLUMN_TYPE_BOOLEAN: _ClassVar[ColumnType]
    COLUMN_TYPE_DOUBLE: _ClassVar[ColumnType]
    COLUMN_TYPE_INTEGER: _ClassVar[ColumnType]
    COLUMN_TYPE_STRING: _ClassVar[ColumnType]

class MlResultDataType(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    ML_RESULT_DATA_TYPE_UNSPECIFIED: _ClassVar[MlResultDataType]
    ML_RESULT_DATA_TYPE_BOOLEAN: _ClassVar[MlResultDataType]
    ML_RESULT_DATA_TYPE_FLOAT16: _ClassVar[MlResultDataType]
    ML_RESULT_DATA_TYPE_FLOAT32: _ClassVar[MlResultDataType]
    ML_RESULT_DATA_TYPE_FLOAT64: _ClassVar[MlResultDataType]
    ML_RESULT_DATA_TYPE_INT32: _ClassVar[MlResultDataType]
    ML_RESULT_DATA_TYPE_INT64: _ClassVar[MlResultDataType]
    ML_RESULT_DATA_TYPE_INT8: _ClassVar[MlResultDataType]
    ML_RESULT_DATA_TYPE_STRING: _ClassVar[MlResultDataType]
    ML_RESULT_DATA_TYPE_UINT8: _ClassVar[MlResultDataType]
    ML_RESULT_DATA_TYPE_UNKNOWN: _ClassVar[MlResultDataType]

class Status(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    STATUS_UNSPECIFIED: _ClassVar[Status]
    STATUS_CANCELLED: _ClassVar[Status]
    STATUS_COMPLETED: _ClassVar[Status]
    STATUS_COMPLETED_WITH_ERROR: _ClassVar[Status]
    STATUS_CREATED: _ClassVar[Status]
    STATUS_FAILED: _ClassVar[Status]
    STATUS_RUNNING: _ClassVar[Status]

class NullValue(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    NULL_VALUE_UNSPECIFIED: _ClassVar[NullValue]
    NULL_VALUE_NULL: _ClassVar[NullValue]
FIELD_VALUE_FACTOR_MODIFIER_UNSPECIFIED: FieldValueFactorModifier
FIELD_VALUE_FACTOR_MODIFIER_LN: FieldValueFactorModifier
FIELD_VALUE_FACTOR_MODIFIER_LN1P: FieldValueFactorModifier
FIELD_VALUE_FACTOR_MODIFIER_LN2P: FieldValueFactorModifier
FIELD_VALUE_FACTOR_MODIFIER_LOG: FieldValueFactorModifier
FIELD_VALUE_FACTOR_MODIFIER_LOG1P: FieldValueFactorModifier
FIELD_VALUE_FACTOR_MODIFIER_LOG2P: FieldValueFactorModifier
FIELD_VALUE_FACTOR_MODIFIER_NONE: FieldValueFactorModifier
FIELD_VALUE_FACTOR_MODIFIER_RECIPROCAL: FieldValueFactorModifier
FIELD_VALUE_FACTOR_MODIFIER_SQRT: FieldValueFactorModifier
FIELD_VALUE_FACTOR_MODIFIER_SQUARE: FieldValueFactorModifier
WAIT_FOR_ACTIVE_SHARD_OPTIONS_UNSPECIFIED: WaitForActiveShardOptions
WAIT_FOR_ACTIVE_SHARD_OPTIONS_ALL: WaitForActiveShardOptions
WAIT_FOR_ACTIVE_SHARD_OPTIONS_NULL: WaitForActiveShardOptions
TOTAL_HITS_RELATION_UNSPECIFIED: TotalHitsRelation
TOTAL_HITS_RELATION_EQ: TotalHitsRelation
TOTAL_HITS_RELATION_GTE: TotalHitsRelation
SCORE_MODE_UNSPECIFIED: ScoreMode
SCORE_MODE_AVG: ScoreMode
SCORE_MODE_MAX: ScoreMode
SCORE_MODE_MIN: ScoreMode
SCORE_MODE_MULTIPLY: ScoreMode
SCORE_MODE_TOTAL: ScoreMode
OP_TYPE_UNSPECIFIED: OpType
OP_TYPE_CREATE: OpType
OP_TYPE_INDEX: OpType
VERSION_TYPE_UNSPECIFIED: VersionType
VERSION_TYPE_EXTERNAL: VersionType
VERSION_TYPE_EXTERNAL_GTE: VersionType
VERSION_TYPE_INTERNAL: VersionType
VERSION_TYPE_FORCE: VersionType
REFRESH_UNSPECIFIED: Refresh
REFRESH_FALSE: Refresh
REFRESH_TRUE: Refresh
REFRESH_WAIT_FOR: Refresh
BUILTIN_SCRIPT_LANGUAGE_UNSPECIFIED: BuiltinScriptLanguage
BUILTIN_SCRIPT_LANGUAGE_EXPRESSION: BuiltinScriptLanguage
BUILTIN_SCRIPT_LANGUAGE_JAVA: BuiltinScriptLanguage
BUILTIN_SCRIPT_LANGUAGE_MUSTACHE: BuiltinScriptLanguage
BUILTIN_SCRIPT_LANGUAGE_PAINLESS: BuiltinScriptLanguage
EXPAND_WILDCARD_UNSPECIFIED: ExpandWildcard
EXPAND_WILDCARD_ALL: ExpandWildcard
EXPAND_WILDCARD_CLOSED: ExpandWildcard
EXPAND_WILDCARD_HIDDEN: ExpandWildcard
EXPAND_WILDCARD_NONE: ExpandWildcard
EXPAND_WILDCARD_OPEN: ExpandWildcard
SEARCH_TYPE_UNSPECIFIED: SearchType
SEARCH_TYPE_DFS_QUERY_THEN_FETCH: SearchType
SEARCH_TYPE_QUERY_THEN_FETCH: SearchType
SUGGEST_MODE_UNSPECIFIED: SuggestMode
SUGGEST_MODE_ALWAYS: SuggestMode
SUGGEST_MODE_MISSING: SuggestMode
SUGGEST_MODE_POPULAR: SuggestMode
RANGE_RELATION_UNSPECIFIED: RangeRelation
RANGE_RELATION_CONTAINS: RangeRelation
RANGE_RELATION_INTERSECTS: RangeRelation
RANGE_RELATION_WITHIN: RangeRelation
TEXT_QUERY_TYPE_UNSPECIFIED: TextQueryType
TEXT_QUERY_TYPE_BEST_FIELDS: TextQueryType
TEXT_QUERY_TYPE_BOOL_PREFIX: TextQueryType
TEXT_QUERY_TYPE_CROSS_FIELDS: TextQueryType
TEXT_QUERY_TYPE_MOST_FIELDS: TextQueryType
TEXT_QUERY_TYPE_PHRASE: TextQueryType
TEXT_QUERY_TYPE_PHRASE_PREFIX: TextQueryType
ZERO_TERMS_QUERY_UNSPECIFIED: ZeroTermsQuery
ZERO_TERMS_QUERY_ALL: ZeroTermsQuery
ZERO_TERMS_QUERY_NONE: ZeroTermsQuery
TERMS_QUERY_VALUE_TYPE_UNSPECIFIED: TermsQueryValueType
TERMS_QUERY_VALUE_TYPE_BITMAP: TermsQueryValueType
TERMS_QUERY_VALUE_TYPE_DEFAULT: TermsQueryValueType
MULTI_VALUE_MODE_UNSPECIFIED: MultiValueMode
MULTI_VALUE_MODE_AVG: MultiValueMode
MULTI_VALUE_MODE_MAX: MultiValueMode
MULTI_VALUE_MODE_MIN: MultiValueMode
MULTI_VALUE_MODE_SUM: MultiValueMode
FUNCTION_BOOST_MODE_UNSPECIFIED: FunctionBoostMode
FUNCTION_BOOST_MODE_AVG: FunctionBoostMode
FUNCTION_BOOST_MODE_MAX: FunctionBoostMode
FUNCTION_BOOST_MODE_MIN: FunctionBoostMode
FUNCTION_BOOST_MODE_MULTIPLY: FunctionBoostMode
FUNCTION_BOOST_MODE_REPLACE: FunctionBoostMode
FUNCTION_BOOST_MODE_SUM: FunctionBoostMode
FUNCTION_SCORE_MODE_UNSPECIFIED: FunctionScoreMode
FUNCTION_SCORE_MODE_AVG: FunctionScoreMode
FUNCTION_SCORE_MODE_FIRST: FunctionScoreMode
FUNCTION_SCORE_MODE_MAX: FunctionScoreMode
FUNCTION_SCORE_MODE_MIN: FunctionScoreMode
FUNCTION_SCORE_MODE_MULTIPLY: FunctionScoreMode
FUNCTION_SCORE_MODE_SUM: FunctionScoreMode
OPERATOR_UNSPECIFIED: Operator
OPERATOR_AND: Operator
OPERATOR_OR: Operator
MULTI_TERM_QUERY_REWRITE_UNSPECIFIED: MultiTermQueryRewrite
MULTI_TERM_QUERY_REWRITE_CONSTANT_SCORE: MultiTermQueryRewrite
MULTI_TERM_QUERY_REWRITE_CONSTANT_SCORE_BOOLEAN: MultiTermQueryRewrite
MULTI_TERM_QUERY_REWRITE_SCORING_BOOLEAN: MultiTermQueryRewrite
MULTI_TERM_QUERY_REWRITE_TOP_TERMS_N: MultiTermQueryRewrite
MULTI_TERM_QUERY_REWRITE_TOP_TERMS_BLENDED_FREQS_N: MultiTermQueryRewrite
MULTI_TERM_QUERY_REWRITE_TOP_TERMS_BOOST_N: MultiTermQueryRewrite
GEO_VALIDATION_METHOD_UNSPECIFIED: GeoValidationMethod
GEO_VALIDATION_METHOD_COERCE: GeoValidationMethod
GEO_VALIDATION_METHOD_IGNORE_MALFORMED: GeoValidationMethod
GEO_VALIDATION_METHOD_STRICT: GeoValidationMethod
SCRIPT_SORT_TYPE_UNSPECIFIED: ScriptSortType
SCRIPT_SORT_TYPE_NUMBER: ScriptSortType
SCRIPT_SORT_TYPE_STRING: ScriptSortType
SCRIPT_SORT_TYPE_VERSION: ScriptSortType
FIELD_SORT_NUMERIC_TYPE_UNSPECIFIED: FieldSortNumericType
FIELD_SORT_NUMERIC_TYPE_DATE: FieldSortNumericType
FIELD_SORT_NUMERIC_TYPE_DATE_NANOS: FieldSortNumericType
FIELD_SORT_NUMERIC_TYPE_DOUBLE: FieldSortNumericType
FIELD_SORT_NUMERIC_TYPE_LONG: FieldSortNumericType
FIELD_TYPE_UNSPECIFIED: FieldType
FIELD_TYPE_AGGREGATE_METRIC_DOUBLE: FieldType
FIELD_TYPE_ALIAS: FieldType
FIELD_TYPE_BINARY: FieldType
FIELD_TYPE_BOOLEAN: FieldType
FIELD_TYPE_BYTE: FieldType
FIELD_TYPE_COMPLETION: FieldType
FIELD_TYPE_CONSTANT_KEYWORD: FieldType
FIELD_TYPE_DATE: FieldType
FIELD_TYPE_DATE_NANOS: FieldType
FIELD_TYPE_DATE_RANGE: FieldType
FIELD_TYPE_DOUBLE: FieldType
FIELD_TYPE_DOUBLE_RANGE: FieldType
FIELD_TYPE_FLAT_OBJECT: FieldType
FIELD_TYPE_FLOAT: FieldType
FIELD_TYPE_FLOAT_RANGE: FieldType
FIELD_TYPE_GEO_POINT: FieldType
FIELD_TYPE_GEO_SHAPE: FieldType
FIELD_TYPE_HALF_FLOAT: FieldType
FIELD_TYPE_HISTOGRAM: FieldType
FIELD_TYPE_ICU_COLLATION_KEYWORD: FieldType
FIELD_TYPE_INTEGER: FieldType
FIELD_TYPE_INTEGER_RANGE: FieldType
FIELD_TYPE_IP: FieldType
FIELD_TYPE_IP_RANGE: FieldType
FIELD_TYPE_JOIN: FieldType
FIELD_TYPE_KEYWORD: FieldType
FIELD_TYPE_KNN_VECTOR: FieldType
FIELD_TYPE_LONG: FieldType
FIELD_TYPE_LONG_RANGE: FieldType
FIELD_TYPE_MATCH_ONLY_TEXT: FieldType
FIELD_TYPE_MURMUR3: FieldType
FIELD_TYPE_NESTED: FieldType
FIELD_TYPE_OBJECT: FieldType
FIELD_TYPE_PERCOLATOR: FieldType
FIELD_TYPE_RANK_FEATURE: FieldType
FIELD_TYPE_RANK_FEATURES: FieldType
FIELD_TYPE_SCALED_FLOAT: FieldType
FIELD_TYPE_SEARCH_AS_YOU_TYPE: FieldType
FIELD_TYPE_SHORT: FieldType
FIELD_TYPE_TEXT: FieldType
FIELD_TYPE_TOKEN_COUNT: FieldType
FIELD_TYPE_UNSIGNED_LONG: FieldType
FIELD_TYPE_VERSION: FieldType
FIELD_TYPE_WILDCARD: FieldType
FIELD_TYPE_XY_POINT: FieldType
FIELD_TYPE_XY_SHAPE: FieldType
FIELD_TYPE_SEMANTIC: FieldType
SORT_ORDER_UNSPECIFIED: SortOrder
SORT_ORDER_ASC: SortOrder
SORT_ORDER_DESC: SortOrder
SORT_MODE_UNSPECIFIED: SortMode
SORT_MODE_AVG: SortMode
SORT_MODE_MAX: SortMode
SORT_MODE_MEDIAN: SortMode
SORT_MODE_MIN: SortMode
SORT_MODE_SUM: SortMode
GEO_DISTANCE_TYPE_UNSPECIFIED: GeoDistanceType
GEO_DISTANCE_TYPE_ARC: GeoDistanceType
GEO_DISTANCE_TYPE_PLANE: GeoDistanceType
BUILTIN_HIGHLIGHTER_TYPE_UNSPECIFIED: BuiltinHighlighterType
BUILTIN_HIGHLIGHTER_TYPE_PLAIN: BuiltinHighlighterType
BUILTIN_HIGHLIGHTER_TYPE_FVH: BuiltinHighlighterType
BUILTIN_HIGHLIGHTER_TYPE_UNIFIED: BuiltinHighlighterType
BOUNDARY_SCANNER_UNSPECIFIED: BoundaryScanner
BOUNDARY_SCANNER_CHARS: BoundaryScanner
BOUNDARY_SCANNER_SENTENCE: BoundaryScanner
BOUNDARY_SCANNER_WORD: BoundaryScanner
HIGHLIGHTER_FRAGMENTER_UNSPECIFIED: HighlighterFragmenter
HIGHLIGHTER_FRAGMENTER_SIMPLE: HighlighterFragmenter
HIGHLIGHTER_FRAGMENTER_SPAN: HighlighterFragmenter
HIGHLIGHTER_ORDER_UNSPECIFIED: HighlighterOrder
HIGHLIGHTER_ORDER_SCORE: HighlighterOrder
HIGHLIGHTER_TAGS_SCHEMA_UNSPECIFIED: HighlighterTagsSchema
HIGHLIGHTER_TAGS_SCHEMA_STYLED: HighlighterTagsSchema
HIGHLIGHTER_TAGS_SCHEMA_DEFAULT: HighlighterTagsSchema
DISTANCE_UNIT_UNSPECIFIED: DistanceUnit
DISTANCE_UNIT_CM: DistanceUnit
DISTANCE_UNIT_FT: DistanceUnit
DISTANCE_UNIT_IN: DistanceUnit
DISTANCE_UNIT_KM: DistanceUnit
DISTANCE_UNIT_M: DistanceUnit
DISTANCE_UNIT_MI: DistanceUnit
DISTANCE_UNIT_MM: DistanceUnit
DISTANCE_UNIT_NMI: DistanceUnit
DISTANCE_UNIT_YD: DistanceUnit
CHILD_SCORE_MODE_UNSPECIFIED: ChildScoreMode
CHILD_SCORE_MODE_AVG: ChildScoreMode
CHILD_SCORE_MODE_MAX: ChildScoreMode
CHILD_SCORE_MODE_MIN: ChildScoreMode
CHILD_SCORE_MODE_NONE: ChildScoreMode
CHILD_SCORE_MODE_SUM: ChildScoreMode
HIGHLIGHTER_ENCODER_UNSPECIFIED: HighlighterEncoder
HIGHLIGHTER_ENCODER_DEFAULT: HighlighterEncoder
HIGHLIGHTER_ENCODER_HTML: HighlighterEncoder
GEO_EXECUTION_UNSPECIFIED: GeoExecution
GEO_EXECUTION_INDEXED: GeoExecution
GEO_EXECUTION_MEMORY: GeoExecution
TERMS_AGGREGATION_COLLECT_MODE_UNSPECIFIED: TermsAggregationCollectMode
TERMS_AGGREGATION_COLLECT_MODE_BREADTH_FIRST: TermsAggregationCollectMode
TERMS_AGGREGATION_COLLECT_MODE_DEPTH_FIRST: TermsAggregationCollectMode
TERMS_AGGREGATION_EXECUTION_HINT_UNSPECIFIED: TermsAggregationExecutionHint
TERMS_AGGREGATION_EXECUTION_HINT_GLOBAL_ORDINALS: TermsAggregationExecutionHint
TERMS_AGGREGATION_EXECUTION_HINT_GLOBAL_ORDINALS_HASH: TermsAggregationExecutionHint
TERMS_AGGREGATION_EXECUTION_HINT_GLOBAL_ORDINALS_LOW_CARDINALITY: TermsAggregationExecutionHint
TERMS_AGGREGATION_EXECUTION_HINT_MAP: TermsAggregationExecutionHint
VALUE_TYPE_UNSPECIFIED: ValueType
VALUE_TYPE_BOOLEAN: ValueType
VALUE_TYPE_BYTE: ValueType
VALUE_TYPE_DATE: ValueType
VALUE_TYPE_DOUBLE: ValueType
VALUE_TYPE_FLOAT: ValueType
VALUE_TYPE_INTEGER: ValueType
VALUE_TYPE_IP: ValueType
VALUE_TYPE_LONG: ValueType
VALUE_TYPE_NUMBER: ValueType
VALUE_TYPE_NUMERIC: ValueType
VALUE_TYPE_SHORT: ValueType
VALUE_TYPE_STRING: ValueType
VALUE_TYPE_UNSIGNED_LONG: ValueType
BYTE_ORDER_UNSPECIFIED: ByteOrder
BYTE_ORDER_BIG_ENDIAN: ByteOrder
BYTE_ORDER_LITTLE_ENDIAN: ByteOrder
COLUMN_TYPE_UNSPECIFIED: ColumnType
COLUMN_TYPE_BOOLEAN: ColumnType
COLUMN_TYPE_DOUBLE: ColumnType
COLUMN_TYPE_INTEGER: ColumnType
COLUMN_TYPE_STRING: ColumnType
ML_RESULT_DATA_TYPE_UNSPECIFIED: MlResultDataType
ML_RESULT_DATA_TYPE_BOOLEAN: MlResultDataType
ML_RESULT_DATA_TYPE_FLOAT16: MlResultDataType
ML_RESULT_DATA_TYPE_FLOAT32: MlResultDataType
ML_RESULT_DATA_TYPE_FLOAT64: MlResultDataType
ML_RESULT_DATA_TYPE_INT32: MlResultDataType
ML_RESULT_DATA_TYPE_INT64: MlResultDataType
ML_RESULT_DATA_TYPE_INT8: MlResultDataType
ML_RESULT_DATA_TYPE_STRING: MlResultDataType
ML_RESULT_DATA_TYPE_UINT8: MlResultDataType
ML_RESULT_DATA_TYPE_UNKNOWN: MlResultDataType
STATUS_UNSPECIFIED: Status
STATUS_CANCELLED: Status
STATUS_COMPLETED: Status
STATUS_COMPLETED_WITH_ERROR: Status
STATUS_CREATED: Status
STATUS_FAILED: Status
STATUS_RUNNING: Status
NULL_VALUE_UNSPECIFIED: NullValue
NULL_VALUE_NULL: NullValue
TOOLING_SKIP_FIELD_NUMBER: _ClassVar[int]
tooling_skip: _descriptor.FieldDescriptor

class SearchRequest(_message.Message):
    __slots__ = ("index", "x_source", "x_source_excludes", "x_source_includes", "allow_no_indices", "allow_partial_search_results", "analyze_wildcard", "batched_reduce_size", "cancel_after_time_interval", "ccs_minimize_roundtrips", "default_operator", "df", "docvalue_fields", "expand_wildcards", "ignore_throttled", "ignore_unavailable", "max_concurrent_shard_requests", "phase_took", "pre_filter_shard_size", "preference", "q", "request_cache", "total_hits_as_int", "routing", "scroll", "search_type", "suggest_field", "suggest_mode", "suggest_size", "suggest_text", "typed_keys", "search_request_body", "global_params")
    INDEX_FIELD_NUMBER: _ClassVar[int]
    X_SOURCE_FIELD_NUMBER: _ClassVar[int]
    X_SOURCE_EXCLUDES_FIELD_NUMBER: _ClassVar[int]
    X_SOURCE_INCLUDES_FIELD_NUMBER: _ClassVar[int]
    ALLOW_NO_INDICES_FIELD_NUMBER: _ClassVar[int]
    ALLOW_PARTIAL_SEARCH_RESULTS_FIELD_NUMBER: _ClassVar[int]
    ANALYZE_WILDCARD_FIELD_NUMBER: _ClassVar[int]
    BATCHED_REDUCE_SIZE_FIELD_NUMBER: _ClassVar[int]
    CANCEL_AFTER_TIME_INTERVAL_FIELD_NUMBER: _ClassVar[int]
    CCS_MINIMIZE_ROUNDTRIPS_FIELD_NUMBER: _ClassVar[int]
    DEFAULT_OPERATOR_FIELD_NUMBER: _ClassVar[int]
    DF_FIELD_NUMBER: _ClassVar[int]
    DOCVALUE_FIELDS_FIELD_NUMBER: _ClassVar[int]
    EXPAND_WILDCARDS_FIELD_NUMBER: _ClassVar[int]
    IGNORE_THROTTLED_FIELD_NUMBER: _ClassVar[int]
    IGNORE_UNAVAILABLE_FIELD_NUMBER: _ClassVar[int]
    MAX_CONCURRENT_SHARD_REQUESTS_FIELD_NUMBER: _ClassVar[int]
    PHASE_TOOK_FIELD_NUMBER: _ClassVar[int]
    PRE_FILTER_SHARD_SIZE_FIELD_NUMBER: _ClassVar[int]
    PREFERENCE_FIELD_NUMBER: _ClassVar[int]
    Q_FIELD_NUMBER: _ClassVar[int]
    REQUEST_CACHE_FIELD_NUMBER: _ClassVar[int]
    TOTAL_HITS_AS_INT_FIELD_NUMBER: _ClassVar[int]
    ROUTING_FIELD_NUMBER: _ClassVar[int]
    SCROLL_FIELD_NUMBER: _ClassVar[int]
    SEARCH_TYPE_FIELD_NUMBER: _ClassVar[int]
    SUGGEST_FIELD_FIELD_NUMBER: _ClassVar[int]
    SUGGEST_MODE_FIELD_NUMBER: _ClassVar[int]
    SUGGEST_SIZE_FIELD_NUMBER: _ClassVar[int]
    SUGGEST_TEXT_FIELD_NUMBER: _ClassVar[int]
    TYPED_KEYS_FIELD_NUMBER: _ClassVar[int]
    SEARCH_REQUEST_BODY_FIELD_NUMBER: _ClassVar[int]
    GLOBAL_PARAMS_FIELD_NUMBER: _ClassVar[int]
    index: _containers.RepeatedScalarFieldContainer[str]
    x_source: SourceConfigParam
    x_source_excludes: _containers.RepeatedScalarFieldContainer[str]
    x_source_includes: _containers.RepeatedScalarFieldContainer[str]
    allow_no_indices: bool
    allow_partial_search_results: bool
    analyze_wildcard: bool
    batched_reduce_size: int
    cancel_after_time_interval: str
    ccs_minimize_roundtrips: bool
    default_operator: Operator
    df: str
    docvalue_fields: _containers.RepeatedScalarFieldContainer[str]
    expand_wildcards: _containers.RepeatedScalarFieldContainer[ExpandWildcard]
    ignore_throttled: bool
    ignore_unavailable: bool
    max_concurrent_shard_requests: int
    phase_took: bool
    pre_filter_shard_size: int
    preference: str
    q: str
    request_cache: bool
    total_hits_as_int: bool
    routing: _containers.RepeatedScalarFieldContainer[str]
    scroll: str
    search_type: SearchType
    suggest_field: str
    suggest_mode: SuggestMode
    suggest_size: int
    suggest_text: str
    typed_keys: bool
    search_request_body: SearchRequestBody
    global_params: GlobalParams
    def __init__(self, index: _Optional[_Iterable[str]] = ..., x_source: _Optional[_Union[SourceConfigParam, _Mapping]] = ..., x_source_excludes: _Optional[_Iterable[str]] = ..., x_source_includes: _Optional[_Iterable[str]] = ..., allow_no_indices: bool = ..., allow_partial_search_results: bool = ..., analyze_wildcard: bool = ..., batched_reduce_size: _Optional[int] = ..., cancel_after_time_interval: _Optional[str] = ..., ccs_minimize_roundtrips: bool = ..., default_operator: _Optional[_Union[Operator, str]] = ..., df: _Optional[str] = ..., docvalue_fields: _Optional[_Iterable[str]] = ..., expand_wildcards: _Optional[_Iterable[_Union[ExpandWildcard, str]]] = ..., ignore_throttled: bool = ..., ignore_unavailable: bool = ..., max_concurrent_shard_requests: _Optional[int] = ..., phase_took: bool = ..., pre_filter_shard_size: _Optional[int] = ..., preference: _Optional[str] = ..., q: _Optional[str] = ..., request_cache: bool = ..., total_hits_as_int: bool = ..., routing: _Optional[_Iterable[str]] = ..., scroll: _Optional[str] = ..., search_type: _Optional[_Union[SearchType, str]] = ..., suggest_field: _Optional[str] = ..., suggest_mode: _Optional[_Union[SuggestMode, str]] = ..., suggest_size: _Optional[int] = ..., suggest_text: _Optional[str] = ..., typed_keys: bool = ..., search_request_body: _Optional[_Union[SearchRequestBody, _Mapping]] = ..., global_params: _Optional[_Union[GlobalParams, _Mapping]] = ...) -> None: ...

class SearchRequestBody(_message.Message):
    __slots__ = ("collapse", "explain", "ext", "highlight", "track_total_hits", "indices_boost", "docvalue_fields", "min_score", "post_filter", "profile", "search_pipeline", "verbose_pipeline", "query", "rescore", "script_fields", "search_after", "size", "slice", "sort", "x_source", "fields", "terminate_after", "timeout", "track_scores", "include_named_queries_score", "version", "seq_no_primary_term", "stored_fields", "pit", "stats", "derived", "indices_boost_2", "aggregations")
    class IndicesBoostEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: float
        def __init__(self, key: _Optional[str] = ..., value: _Optional[float] = ...) -> None: ...
    class ScriptFieldsEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: ScriptField
        def __init__(self, key: _Optional[str] = ..., value: _Optional[_Union[ScriptField, _Mapping]] = ...) -> None: ...
    class DerivedEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: DerivedField
        def __init__(self, key: _Optional[str] = ..., value: _Optional[_Union[DerivedField, _Mapping]] = ...) -> None: ...
    class AggregationsEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: AggregationContainer
        def __init__(self, key: _Optional[str] = ..., value: _Optional[_Union[AggregationContainer, _Mapping]] = ...) -> None: ...
    COLLAPSE_FIELD_NUMBER: _ClassVar[int]
    EXPLAIN_FIELD_NUMBER: _ClassVar[int]
    EXT_FIELD_NUMBER: _ClassVar[int]
    FROM_FIELD_NUMBER: _ClassVar[int]
    HIGHLIGHT_FIELD_NUMBER: _ClassVar[int]
    TRACK_TOTAL_HITS_FIELD_NUMBER: _ClassVar[int]
    INDICES_BOOST_FIELD_NUMBER: _ClassVar[int]
    DOCVALUE_FIELDS_FIELD_NUMBER: _ClassVar[int]
    MIN_SCORE_FIELD_NUMBER: _ClassVar[int]
    POST_FILTER_FIELD_NUMBER: _ClassVar[int]
    PROFILE_FIELD_NUMBER: _ClassVar[int]
    SEARCH_PIPELINE_FIELD_NUMBER: _ClassVar[int]
    VERBOSE_PIPELINE_FIELD_NUMBER: _ClassVar[int]
    QUERY_FIELD_NUMBER: _ClassVar[int]
    RESCORE_FIELD_NUMBER: _ClassVar[int]
    SCRIPT_FIELDS_FIELD_NUMBER: _ClassVar[int]
    SEARCH_AFTER_FIELD_NUMBER: _ClassVar[int]
    SIZE_FIELD_NUMBER: _ClassVar[int]
    SLICE_FIELD_NUMBER: _ClassVar[int]
    SORT_FIELD_NUMBER: _ClassVar[int]
    X_SOURCE_FIELD_NUMBER: _ClassVar[int]
    FIELDS_FIELD_NUMBER: _ClassVar[int]
    TERMINATE_AFTER_FIELD_NUMBER: _ClassVar[int]
    TIMEOUT_FIELD_NUMBER: _ClassVar[int]
    TRACK_SCORES_FIELD_NUMBER: _ClassVar[int]
    INCLUDE_NAMED_QUERIES_SCORE_FIELD_NUMBER: _ClassVar[int]
    VERSION_FIELD_NUMBER: _ClassVar[int]
    SEQ_NO_PRIMARY_TERM_FIELD_NUMBER: _ClassVar[int]
    STORED_FIELDS_FIELD_NUMBER: _ClassVar[int]
    PIT_FIELD_NUMBER: _ClassVar[int]
    STATS_FIELD_NUMBER: _ClassVar[int]
    DERIVED_FIELD_NUMBER: _ClassVar[int]
    INDICES_BOOST_2_FIELD_NUMBER: _ClassVar[int]
    AGGREGATIONS_FIELD_NUMBER: _ClassVar[int]
    collapse: FieldCollapse
    explain: bool
    ext: ObjectMap
    highlight: Highlight
    track_total_hits: TrackHits
    indices_boost: _containers.ScalarMap[str, float]
    docvalue_fields: _containers.RepeatedCompositeFieldContainer[FieldAndFormat]
    min_score: float
    post_filter: QueryContainer
    profile: bool
    search_pipeline: str
    verbose_pipeline: bool
    query: QueryContainer
    rescore: _containers.RepeatedCompositeFieldContainer[Rescore]
    script_fields: _containers.MessageMap[str, ScriptField]
    search_after: _containers.RepeatedCompositeFieldContainer[FieldValue]
    size: int
    slice: SlicedScroll
    sort: _containers.RepeatedCompositeFieldContainer[SortCombinations]
    x_source: SourceConfig
    fields: _containers.RepeatedCompositeFieldContainer[FieldAndFormat]
    terminate_after: int
    timeout: str
    track_scores: bool
    include_named_queries_score: bool
    version: bool
    seq_no_primary_term: bool
    stored_fields: _containers.RepeatedScalarFieldContainer[str]
    pit: PointInTimeReference
    stats: _containers.RepeatedScalarFieldContainer[str]
    derived: _containers.MessageMap[str, DerivedField]
    indices_boost_2: _containers.RepeatedCompositeFieldContainer[FloatMap]
    aggregations: _containers.MessageMap[str, AggregationContainer]
    def __init__(self, collapse: _Optional[_Union[FieldCollapse, _Mapping]] = ..., explain: bool = ..., ext: _Optional[_Union[ObjectMap, _Mapping]] = ..., highlight: _Optional[_Union[Highlight, _Mapping]] = ..., track_total_hits: _Optional[_Union[TrackHits, _Mapping]] = ..., indices_boost: _Optional[_Mapping[str, float]] = ..., docvalue_fields: _Optional[_Iterable[_Union[FieldAndFormat, _Mapping]]] = ..., min_score: _Optional[float] = ..., post_filter: _Optional[_Union[QueryContainer, _Mapping]] = ..., profile: bool = ..., search_pipeline: _Optional[str] = ..., verbose_pipeline: bool = ..., query: _Optional[_Union[QueryContainer, _Mapping]] = ..., rescore: _Optional[_Iterable[_Union[Rescore, _Mapping]]] = ..., script_fields: _Optional[_Mapping[str, ScriptField]] = ..., search_after: _Optional[_Iterable[_Union[FieldValue, _Mapping]]] = ..., size: _Optional[int] = ..., slice: _Optional[_Union[SlicedScroll, _Mapping]] = ..., sort: _Optional[_Iterable[_Union[SortCombinations, _Mapping]]] = ..., x_source: _Optional[_Union[SourceConfig, _Mapping]] = ..., fields: _Optional[_Iterable[_Union[FieldAndFormat, _Mapping]]] = ..., terminate_after: _Optional[int] = ..., timeout: _Optional[str] = ..., track_scores: bool = ..., include_named_queries_score: bool = ..., version: bool = ..., seq_no_primary_term: bool = ..., stored_fields: _Optional[_Iterable[str]] = ..., pit: _Optional[_Union[PointInTimeReference, _Mapping]] = ..., stats: _Optional[_Iterable[str]] = ..., derived: _Optional[_Mapping[str, DerivedField]] = ..., indices_boost_2: _Optional[_Iterable[_Union[FloatMap, _Mapping]]] = ..., aggregations: _Optional[_Mapping[str, AggregationContainer]] = ..., **kwargs) -> None: ...

class DerivedField(_message.Message):
    __slots__ = ("name", "type", "script", "prefilter_field", "properties", "ignore_malformed", "format")
    NAME_FIELD_NUMBER: _ClassVar[int]
    TYPE_FIELD_NUMBER: _ClassVar[int]
    SCRIPT_FIELD_NUMBER: _ClassVar[int]
    PREFILTER_FIELD_FIELD_NUMBER: _ClassVar[int]
    PROPERTIES_FIELD_NUMBER: _ClassVar[int]
    IGNORE_MALFORMED_FIELD_NUMBER: _ClassVar[int]
    FORMAT_FIELD_NUMBER: _ClassVar[int]
    name: str
    type: str
    script: Script
    prefilter_field: str
    properties: ObjectMap
    ignore_malformed: bool
    format: str
    def __init__(self, name: _Optional[str] = ..., type: _Optional[str] = ..., script: _Optional[_Union[Script, _Mapping]] = ..., prefilter_field: _Optional[str] = ..., properties: _Optional[_Union[ObjectMap, _Mapping]] = ..., ignore_malformed: bool = ..., format: _Optional[str] = ...) -> None: ...

class TrackHits(_message.Message):
    __slots__ = ("enabled", "count")
    ENABLED_FIELD_NUMBER: _ClassVar[int]
    COUNT_FIELD_NUMBER: _ClassVar[int]
    enabled: bool
    count: int
    def __init__(self, enabled: bool = ..., count: _Optional[int] = ...) -> None: ...

class SearchResponse(_message.Message):
    __slots__ = ("took", "timed_out", "x_shards", "phase_took", "hits", "processor_results", "x_clusters", "fields", "num_reduce_phases", "profile", "pit_id", "x_scroll_id", "terminated_early", "aggregations")
    class AggregationsEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: Aggregate
        def __init__(self, key: _Optional[str] = ..., value: _Optional[_Union[Aggregate, _Mapping]] = ...) -> None: ...
    TOOK_FIELD_NUMBER: _ClassVar[int]
    TIMED_OUT_FIELD_NUMBER: _ClassVar[int]
    X_SHARDS_FIELD_NUMBER: _ClassVar[int]
    PHASE_TOOK_FIELD_NUMBER: _ClassVar[int]
    HITS_FIELD_NUMBER: _ClassVar[int]
    PROCESSOR_RESULTS_FIELD_NUMBER: _ClassVar[int]
    X_CLUSTERS_FIELD_NUMBER: _ClassVar[int]
    FIELDS_FIELD_NUMBER: _ClassVar[int]
    NUM_REDUCE_PHASES_FIELD_NUMBER: _ClassVar[int]
    PROFILE_FIELD_NUMBER: _ClassVar[int]
    PIT_ID_FIELD_NUMBER: _ClassVar[int]
    X_SCROLL_ID_FIELD_NUMBER: _ClassVar[int]
    TERMINATED_EARLY_FIELD_NUMBER: _ClassVar[int]
    AGGREGATIONS_FIELD_NUMBER: _ClassVar[int]
    took: int
    timed_out: bool
    x_shards: ShardStatistics
    phase_took: PhaseTook
    hits: HitsMetadata
    processor_results: _containers.RepeatedCompositeFieldContainer[ProcessorExecutionDetail]
    x_clusters: ClusterStatistics
    fields: ObjectMap
    num_reduce_phases: int
    profile: Profile
    pit_id: str
    x_scroll_id: str
    terminated_early: bool
    aggregations: _containers.MessageMap[str, Aggregate]
    def __init__(self, took: _Optional[int] = ..., timed_out: bool = ..., x_shards: _Optional[_Union[ShardStatistics, _Mapping]] = ..., phase_took: _Optional[_Union[PhaseTook, _Mapping]] = ..., hits: _Optional[_Union[HitsMetadata, _Mapping]] = ..., processor_results: _Optional[_Iterable[_Union[ProcessorExecutionDetail, _Mapping]]] = ..., x_clusters: _Optional[_Union[ClusterStatistics, _Mapping]] = ..., fields: _Optional[_Union[ObjectMap, _Mapping]] = ..., num_reduce_phases: _Optional[int] = ..., profile: _Optional[_Union[Profile, _Mapping]] = ..., pit_id: _Optional[str] = ..., x_scroll_id: _Optional[str] = ..., terminated_early: bool = ..., aggregations: _Optional[_Mapping[str, Aggregate]] = ...) -> None: ...

class ProcessorExecutionDetail(_message.Message):
    __slots__ = ("processor_name", "duration_millis", "input_data", "output_data", "status", "tag", "error")
    PROCESSOR_NAME_FIELD_NUMBER: _ClassVar[int]
    DURATION_MILLIS_FIELD_NUMBER: _ClassVar[int]
    INPUT_DATA_FIELD_NUMBER: _ClassVar[int]
    OUTPUT_DATA_FIELD_NUMBER: _ClassVar[int]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    TAG_FIELD_NUMBER: _ClassVar[int]
    ERROR_FIELD_NUMBER: _ClassVar[int]
    processor_name: str
    duration_millis: int
    input_data: ObjectMap
    output_data: ObjectMap
    status: str
    tag: str
    error: str
    def __init__(self, processor_name: _Optional[str] = ..., duration_millis: _Optional[int] = ..., input_data: _Optional[_Union[ObjectMap, _Mapping]] = ..., output_data: _Optional[_Union[ObjectMap, _Mapping]] = ..., status: _Optional[str] = ..., tag: _Optional[str] = ..., error: _Optional[str] = ...) -> None: ...

class PhaseTook(_message.Message):
    __slots__ = ("dfs_pre_query", "query", "fetch", "dfs_query", "expand", "can_match")
    DFS_PRE_QUERY_FIELD_NUMBER: _ClassVar[int]
    QUERY_FIELD_NUMBER: _ClassVar[int]
    FETCH_FIELD_NUMBER: _ClassVar[int]
    DFS_QUERY_FIELD_NUMBER: _ClassVar[int]
    EXPAND_FIELD_NUMBER: _ClassVar[int]
    CAN_MATCH_FIELD_NUMBER: _ClassVar[int]
    dfs_pre_query: int
    query: int
    fetch: int
    dfs_query: int
    expand: int
    can_match: int
    def __init__(self, dfs_pre_query: _Optional[int] = ..., query: _Optional[int] = ..., fetch: _Optional[int] = ..., dfs_query: _Optional[int] = ..., expand: _Optional[int] = ..., can_match: _Optional[int] = ...) -> None: ...

class HitsMetadataTotal(_message.Message):
    __slots__ = ("total_hits", "int64")
    TOTAL_HITS_FIELD_NUMBER: _ClassVar[int]
    INT64_FIELD_NUMBER: _ClassVar[int]
    total_hits: TotalHits
    int64: int
    def __init__(self, total_hits: _Optional[_Union[TotalHits, _Mapping]] = ..., int64: _Optional[int] = ...) -> None: ...

class HitsMetadataMaxScore(_message.Message):
    __slots__ = ("float", "null_value")
    FLOAT_FIELD_NUMBER: _ClassVar[int]
    NULL_VALUE_FIELD_NUMBER: _ClassVar[int]
    float: float
    null_value: NullValue
    def __init__(self, float: _Optional[float] = ..., null_value: _Optional[_Union[NullValue, str]] = ...) -> None: ...

class HitsMetadata(_message.Message):
    __slots__ = ("total", "hits", "max_score")
    TOTAL_FIELD_NUMBER: _ClassVar[int]
    HITS_FIELD_NUMBER: _ClassVar[int]
    MAX_SCORE_FIELD_NUMBER: _ClassVar[int]
    total: HitsMetadataTotal
    hits: _containers.RepeatedCompositeFieldContainer[HitsMetadataHitsInner]
    max_score: HitsMetadataMaxScore
    def __init__(self, total: _Optional[_Union[HitsMetadataTotal, _Mapping]] = ..., hits: _Optional[_Iterable[_Union[HitsMetadataHitsInner, _Mapping]]] = ..., max_score: _Optional[_Union[HitsMetadataMaxScore, _Mapping]] = ...) -> None: ...

class TotalHits(_message.Message):
    __slots__ = ("relation", "value")
    RELATION_FIELD_NUMBER: _ClassVar[int]
    VALUE_FIELD_NUMBER: _ClassVar[int]
    relation: TotalHitsRelation
    value: int
    def __init__(self, relation: _Optional[_Union[TotalHitsRelation, str]] = ..., value: _Optional[int] = ...) -> None: ...

class InnerHitsResult(_message.Message):
    __slots__ = ("hits",)
    HITS_FIELD_NUMBER: _ClassVar[int]
    hits: HitsMetadata
    def __init__(self, hits: _Optional[_Union[HitsMetadata, _Mapping]] = ...) -> None: ...

class HitXScore(_message.Message):
    __slots__ = ("null_value", "double")
    NULL_VALUE_FIELD_NUMBER: _ClassVar[int]
    DOUBLE_FIELD_NUMBER: _ClassVar[int]
    null_value: NullValue
    double: float
    def __init__(self, null_value: _Optional[_Union[NullValue, str]] = ..., double: _Optional[float] = ...) -> None: ...

class HitsMetadataHitsInner(_message.Message):
    __slots__ = ("x_type", "x_index", "x_id", "x_score", "x_explanation", "fields", "highlight", "inner_hits", "matched_queries", "x_nested", "x_ignored", "ignored_field_values", "x_shard", "x_node", "x_routing", "x_source", "x_seq_no", "x_primary_term", "x_version", "sort", "meta_fields", "matched_queries_2")
    class HighlightEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: StringArray
        def __init__(self, key: _Optional[str] = ..., value: _Optional[_Union[StringArray, _Mapping]] = ...) -> None: ...
    class InnerHitsEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: InnerHitsResult
        def __init__(self, key: _Optional[str] = ..., value: _Optional[_Union[InnerHitsResult, _Mapping]] = ...) -> None: ...
    class IgnoredFieldValuesEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: StringArray
        def __init__(self, key: _Optional[str] = ..., value: _Optional[_Union[StringArray, _Mapping]] = ...) -> None: ...
    X_TYPE_FIELD_NUMBER: _ClassVar[int]
    X_INDEX_FIELD_NUMBER: _ClassVar[int]
    X_ID_FIELD_NUMBER: _ClassVar[int]
    X_SCORE_FIELD_NUMBER: _ClassVar[int]
    X_EXPLANATION_FIELD_NUMBER: _ClassVar[int]
    FIELDS_FIELD_NUMBER: _ClassVar[int]
    HIGHLIGHT_FIELD_NUMBER: _ClassVar[int]
    INNER_HITS_FIELD_NUMBER: _ClassVar[int]
    MATCHED_QUERIES_FIELD_NUMBER: _ClassVar[int]
    X_NESTED_FIELD_NUMBER: _ClassVar[int]
    X_IGNORED_FIELD_NUMBER: _ClassVar[int]
    IGNORED_FIELD_VALUES_FIELD_NUMBER: _ClassVar[int]
    X_SHARD_FIELD_NUMBER: _ClassVar[int]
    X_NODE_FIELD_NUMBER: _ClassVar[int]
    X_ROUTING_FIELD_NUMBER: _ClassVar[int]
    X_SOURCE_FIELD_NUMBER: _ClassVar[int]
    X_SEQ_NO_FIELD_NUMBER: _ClassVar[int]
    X_PRIMARY_TERM_FIELD_NUMBER: _ClassVar[int]
    X_VERSION_FIELD_NUMBER: _ClassVar[int]
    SORT_FIELD_NUMBER: _ClassVar[int]
    META_FIELDS_FIELD_NUMBER: _ClassVar[int]
    MATCHED_QUERIES_2_FIELD_NUMBER: _ClassVar[int]
    x_type: str
    x_index: str
    x_id: str
    x_score: HitXScore
    x_explanation: Explanation
    fields: ObjectMap
    highlight: _containers.MessageMap[str, StringArray]
    inner_hits: _containers.MessageMap[str, InnerHitsResult]
    matched_queries: _containers.RepeatedScalarFieldContainer[str]
    x_nested: NestedIdentity
    x_ignored: _containers.RepeatedScalarFieldContainer[str]
    ignored_field_values: _containers.MessageMap[str, StringArray]
    x_shard: str
    x_node: str
    x_routing: str
    x_source: bytes
    x_seq_no: int
    x_primary_term: int
    x_version: int
    sort: _containers.RepeatedCompositeFieldContainer[FieldValue]
    meta_fields: ObjectMap
    matched_queries_2: HitMatchedQueries
    def __init__(self, x_type: _Optional[str] = ..., x_index: _Optional[str] = ..., x_id: _Optional[str] = ..., x_score: _Optional[_Union[HitXScore, _Mapping]] = ..., x_explanation: _Optional[_Union[Explanation, _Mapping]] = ..., fields: _Optional[_Union[ObjectMap, _Mapping]] = ..., highlight: _Optional[_Mapping[str, StringArray]] = ..., inner_hits: _Optional[_Mapping[str, InnerHitsResult]] = ..., matched_queries: _Optional[_Iterable[str]] = ..., x_nested: _Optional[_Union[NestedIdentity, _Mapping]] = ..., x_ignored: _Optional[_Iterable[str]] = ..., ignored_field_values: _Optional[_Mapping[str, StringArray]] = ..., x_shard: _Optional[str] = ..., x_node: _Optional[str] = ..., x_routing: _Optional[str] = ..., x_source: _Optional[bytes] = ..., x_seq_no: _Optional[int] = ..., x_primary_term: _Optional[int] = ..., x_version: _Optional[int] = ..., sort: _Optional[_Iterable[_Union[FieldValue, _Mapping]]] = ..., meta_fields: _Optional[_Union[ObjectMap, _Mapping]] = ..., matched_queries_2: _Optional[_Union[HitMatchedQueries, _Mapping]] = ...) -> None: ...

class ClusterStatistics(_message.Message):
    __slots__ = ("skipped", "successful", "total")
    SKIPPED_FIELD_NUMBER: _ClassVar[int]
    SUCCESSFUL_FIELD_NUMBER: _ClassVar[int]
    TOTAL_FIELD_NUMBER: _ClassVar[int]
    skipped: int
    successful: int
    total: int
    def __init__(self, skipped: _Optional[int] = ..., successful: _Optional[int] = ..., total: _Optional[int] = ...) -> None: ...

class Profile(_message.Message):
    __slots__ = ("shards",)
    SHARDS_FIELD_NUMBER: _ClassVar[int]
    shards: _containers.RepeatedCompositeFieldContainer[ShardProfile]
    def __init__(self, shards: _Optional[_Iterable[_Union[ShardProfile, _Mapping]]] = ...) -> None: ...

class RescoreQuery(_message.Message):
    __slots__ = ("rescore_query", "query_weight", "rescore_query_weight", "score_mode")
    RESCORE_QUERY_FIELD_NUMBER: _ClassVar[int]
    QUERY_WEIGHT_FIELD_NUMBER: _ClassVar[int]
    RESCORE_QUERY_WEIGHT_FIELD_NUMBER: _ClassVar[int]
    SCORE_MODE_FIELD_NUMBER: _ClassVar[int]
    rescore_query: QueryContainer
    query_weight: float
    rescore_query_weight: float
    score_mode: ScoreMode
    def __init__(self, rescore_query: _Optional[_Union[QueryContainer, _Mapping]] = ..., query_weight: _Optional[float] = ..., rescore_query_weight: _Optional[float] = ..., score_mode: _Optional[_Union[ScoreMode, str]] = ...) -> None: ...

class Rescore(_message.Message):
    __slots__ = ("query", "window_size")
    QUERY_FIELD_NUMBER: _ClassVar[int]
    WINDOW_SIZE_FIELD_NUMBER: _ClassVar[int]
    query: RescoreQuery
    window_size: int
    def __init__(self, query: _Optional[_Union[RescoreQuery, _Mapping]] = ..., window_size: _Optional[int] = ...) -> None: ...

class SlicedScroll(_message.Message):
    __slots__ = ("field", "id", "max")
    FIELD_FIELD_NUMBER: _ClassVar[int]
    ID_FIELD_NUMBER: _ClassVar[int]
    MAX_FIELD_NUMBER: _ClassVar[int]
    field: str
    id: int
    max: int
    def __init__(self, field: _Optional[str] = ..., id: _Optional[int] = ..., max: _Optional[int] = ...) -> None: ...

class ShardProfile(_message.Message):
    __slots__ = ("aggregations", "id", "searches", "fetch")
    AGGREGATIONS_FIELD_NUMBER: _ClassVar[int]
    ID_FIELD_NUMBER: _ClassVar[int]
    SEARCHES_FIELD_NUMBER: _ClassVar[int]
    FETCH_FIELD_NUMBER: _ClassVar[int]
    aggregations: _containers.RepeatedCompositeFieldContainer[AggregationProfile]
    id: str
    searches: _containers.RepeatedCompositeFieldContainer[SearchProfile]
    fetch: FetchProfile
    def __init__(self, aggregations: _Optional[_Iterable[_Union[AggregationProfile, _Mapping]]] = ..., id: _Optional[str] = ..., searches: _Optional[_Iterable[_Union[SearchProfile, _Mapping]]] = ..., fetch: _Optional[_Union[FetchProfile, _Mapping]] = ...) -> None: ...

class AggregationProfile(_message.Message):
    __slots__ = ("breakdown", "description", "time_in_nanos", "type", "debug", "children")
    BREAKDOWN_FIELD_NUMBER: _ClassVar[int]
    DESCRIPTION_FIELD_NUMBER: _ClassVar[int]
    TIME_IN_NANOS_FIELD_NUMBER: _ClassVar[int]
    TYPE_FIELD_NUMBER: _ClassVar[int]
    DEBUG_FIELD_NUMBER: _ClassVar[int]
    CHILDREN_FIELD_NUMBER: _ClassVar[int]
    breakdown: AggregationBreakdown
    description: str
    time_in_nanos: int
    type: str
    debug: AggregationProfileDebug
    children: _containers.RepeatedCompositeFieldContainer[AggregationProfile]
    def __init__(self, breakdown: _Optional[_Union[AggregationBreakdown, _Mapping]] = ..., description: _Optional[str] = ..., time_in_nanos: _Optional[int] = ..., type: _Optional[str] = ..., debug: _Optional[_Union[AggregationProfileDebug, _Mapping]] = ..., children: _Optional[_Iterable[_Union[AggregationProfile, _Mapping]]] = ...) -> None: ...

class AggregationBreakdown(_message.Message):
    __slots__ = ("build_aggregation", "build_aggregation_count", "build_leaf_collector", "build_leaf_collector_count", "collect", "collect_count", "initialize", "initialize_count", "post_collection", "post_collection_count", "reduce", "reduce_count")
    BUILD_AGGREGATION_FIELD_NUMBER: _ClassVar[int]
    BUILD_AGGREGATION_COUNT_FIELD_NUMBER: _ClassVar[int]
    BUILD_LEAF_COLLECTOR_FIELD_NUMBER: _ClassVar[int]
    BUILD_LEAF_COLLECTOR_COUNT_FIELD_NUMBER: _ClassVar[int]
    COLLECT_FIELD_NUMBER: _ClassVar[int]
    COLLECT_COUNT_FIELD_NUMBER: _ClassVar[int]
    INITIALIZE_FIELD_NUMBER: _ClassVar[int]
    INITIALIZE_COUNT_FIELD_NUMBER: _ClassVar[int]
    POST_COLLECTION_FIELD_NUMBER: _ClassVar[int]
    POST_COLLECTION_COUNT_FIELD_NUMBER: _ClassVar[int]
    REDUCE_FIELD_NUMBER: _ClassVar[int]
    REDUCE_COUNT_FIELD_NUMBER: _ClassVar[int]
    build_aggregation: int
    build_aggregation_count: int
    build_leaf_collector: int
    build_leaf_collector_count: int
    collect: int
    collect_count: int
    initialize: int
    initialize_count: int
    post_collection: int
    post_collection_count: int
    reduce: int
    reduce_count: int
    def __init__(self, build_aggregation: _Optional[int] = ..., build_aggregation_count: _Optional[int] = ..., build_leaf_collector: _Optional[int] = ..., build_leaf_collector_count: _Optional[int] = ..., collect: _Optional[int] = ..., collect_count: _Optional[int] = ..., initialize: _Optional[int] = ..., initialize_count: _Optional[int] = ..., post_collection: _Optional[int] = ..., post_collection_count: _Optional[int] = ..., reduce: _Optional[int] = ..., reduce_count: _Optional[int] = ...) -> None: ...

class SearchProfile(_message.Message):
    __slots__ = ("collector", "query", "rewrite_time")
    COLLECTOR_FIELD_NUMBER: _ClassVar[int]
    QUERY_FIELD_NUMBER: _ClassVar[int]
    REWRITE_TIME_FIELD_NUMBER: _ClassVar[int]
    collector: _containers.RepeatedCompositeFieldContainer[Collector]
    query: _containers.RepeatedCompositeFieldContainer[QueryProfile]
    rewrite_time: int
    def __init__(self, collector: _Optional[_Iterable[_Union[Collector, _Mapping]]] = ..., query: _Optional[_Iterable[_Union[QueryProfile, _Mapping]]] = ..., rewrite_time: _Optional[int] = ...) -> None: ...

class PointInTimeReference(_message.Message):
    __slots__ = ("id", "keep_alive")
    ID_FIELD_NUMBER: _ClassVar[int]
    KEEP_ALIVE_FIELD_NUMBER: _ClassVar[int]
    id: str
    keep_alive: str
    def __init__(self, id: _Optional[str] = ..., keep_alive: _Optional[str] = ...) -> None: ...

class Collector(_message.Message):
    __slots__ = ("name", "reason", "time_in_nanos", "children")
    NAME_FIELD_NUMBER: _ClassVar[int]
    REASON_FIELD_NUMBER: _ClassVar[int]
    TIME_IN_NANOS_FIELD_NUMBER: _ClassVar[int]
    CHILDREN_FIELD_NUMBER: _ClassVar[int]
    name: str
    reason: str
    time_in_nanos: int
    children: _containers.RepeatedCompositeFieldContainer[Collector]
    def __init__(self, name: _Optional[str] = ..., reason: _Optional[str] = ..., time_in_nanos: _Optional[int] = ..., children: _Optional[_Iterable[_Union[Collector, _Mapping]]] = ...) -> None: ...

class QueryProfile(_message.Message):
    __slots__ = ("breakdown", "description", "time_in_nanos", "type", "children")
    BREAKDOWN_FIELD_NUMBER: _ClassVar[int]
    DESCRIPTION_FIELD_NUMBER: _ClassVar[int]
    TIME_IN_NANOS_FIELD_NUMBER: _ClassVar[int]
    TYPE_FIELD_NUMBER: _ClassVar[int]
    CHILDREN_FIELD_NUMBER: _ClassVar[int]
    breakdown: QueryBreakdown
    description: str
    time_in_nanos: int
    type: str
    children: _containers.RepeatedCompositeFieldContainer[QueryProfile]
    def __init__(self, breakdown: _Optional[_Union[QueryBreakdown, _Mapping]] = ..., description: _Optional[str] = ..., time_in_nanos: _Optional[int] = ..., type: _Optional[str] = ..., children: _Optional[_Iterable[_Union[QueryProfile, _Mapping]]] = ...) -> None: ...

class QueryBreakdown(_message.Message):
    __slots__ = ("advance", "advance_count", "build_scorer", "build_scorer_count", "create_weight", "create_weight_count", "match", "match_count", "shallow_advance", "shallow_advance_count", "next_doc", "next_doc_count", "score", "score_count", "compute_max_score", "compute_max_score_count", "set_min_competitive_score", "set_min_competitive_score_count")
    ADVANCE_FIELD_NUMBER: _ClassVar[int]
    ADVANCE_COUNT_FIELD_NUMBER: _ClassVar[int]
    BUILD_SCORER_FIELD_NUMBER: _ClassVar[int]
    BUILD_SCORER_COUNT_FIELD_NUMBER: _ClassVar[int]
    CREATE_WEIGHT_FIELD_NUMBER: _ClassVar[int]
    CREATE_WEIGHT_COUNT_FIELD_NUMBER: _ClassVar[int]
    MATCH_FIELD_NUMBER: _ClassVar[int]
    MATCH_COUNT_FIELD_NUMBER: _ClassVar[int]
    SHALLOW_ADVANCE_FIELD_NUMBER: _ClassVar[int]
    SHALLOW_ADVANCE_COUNT_FIELD_NUMBER: _ClassVar[int]
    NEXT_DOC_FIELD_NUMBER: _ClassVar[int]
    NEXT_DOC_COUNT_FIELD_NUMBER: _ClassVar[int]
    SCORE_FIELD_NUMBER: _ClassVar[int]
    SCORE_COUNT_FIELD_NUMBER: _ClassVar[int]
    COMPUTE_MAX_SCORE_FIELD_NUMBER: _ClassVar[int]
    COMPUTE_MAX_SCORE_COUNT_FIELD_NUMBER: _ClassVar[int]
    SET_MIN_COMPETITIVE_SCORE_FIELD_NUMBER: _ClassVar[int]
    SET_MIN_COMPETITIVE_SCORE_COUNT_FIELD_NUMBER: _ClassVar[int]
    advance: int
    advance_count: int
    build_scorer: int
    build_scorer_count: int
    create_weight: int
    create_weight_count: int
    match: int
    match_count: int
    shallow_advance: int
    shallow_advance_count: int
    next_doc: int
    next_doc_count: int
    score: int
    score_count: int
    compute_max_score: int
    compute_max_score_count: int
    set_min_competitive_score: int
    set_min_competitive_score_count: int
    def __init__(self, advance: _Optional[int] = ..., advance_count: _Optional[int] = ..., build_scorer: _Optional[int] = ..., build_scorer_count: _Optional[int] = ..., create_weight: _Optional[int] = ..., create_weight_count: _Optional[int] = ..., match: _Optional[int] = ..., match_count: _Optional[int] = ..., shallow_advance: _Optional[int] = ..., shallow_advance_count: _Optional[int] = ..., next_doc: _Optional[int] = ..., next_doc_count: _Optional[int] = ..., score: _Optional[int] = ..., score_count: _Optional[int] = ..., compute_max_score: _Optional[int] = ..., compute_max_score_count: _Optional[int] = ..., set_min_competitive_score: _Optional[int] = ..., set_min_competitive_score_count: _Optional[int] = ...) -> None: ...

class FetchProfileDebug(_message.Message):
    __slots__ = ("stored_fields", "fast_path")
    STORED_FIELDS_FIELD_NUMBER: _ClassVar[int]
    FAST_PATH_FIELD_NUMBER: _ClassVar[int]
    stored_fields: _containers.RepeatedScalarFieldContainer[str]
    fast_path: int
    def __init__(self, stored_fields: _Optional[_Iterable[str]] = ..., fast_path: _Optional[int] = ...) -> None: ...

class FetchProfile(_message.Message):
    __slots__ = ("type", "description", "time_in_nanos", "breakdown", "debug", "children")
    TYPE_FIELD_NUMBER: _ClassVar[int]
    DESCRIPTION_FIELD_NUMBER: _ClassVar[int]
    TIME_IN_NANOS_FIELD_NUMBER: _ClassVar[int]
    BREAKDOWN_FIELD_NUMBER: _ClassVar[int]
    DEBUG_FIELD_NUMBER: _ClassVar[int]
    CHILDREN_FIELD_NUMBER: _ClassVar[int]
    type: str
    description: str
    time_in_nanos: int
    breakdown: FetchProfileBreakdown
    debug: FetchProfileDebug
    children: _containers.RepeatedCompositeFieldContainer[FetchProfile]
    def __init__(self, type: _Optional[str] = ..., description: _Optional[str] = ..., time_in_nanos: _Optional[int] = ..., breakdown: _Optional[_Union[FetchProfileBreakdown, _Mapping]] = ..., debug: _Optional[_Union[FetchProfileDebug, _Mapping]] = ..., children: _Optional[_Iterable[_Union[FetchProfile, _Mapping]]] = ...) -> None: ...

class FetchProfileBreakdown(_message.Message):
    __slots__ = ("load_source", "load_source_count", "load_stored_fields", "load_stored_fields_count", "next_reader", "next_reader_count", "process_count", "process")
    LOAD_SOURCE_FIELD_NUMBER: _ClassVar[int]
    LOAD_SOURCE_COUNT_FIELD_NUMBER: _ClassVar[int]
    LOAD_STORED_FIELDS_FIELD_NUMBER: _ClassVar[int]
    LOAD_STORED_FIELDS_COUNT_FIELD_NUMBER: _ClassVar[int]
    NEXT_READER_FIELD_NUMBER: _ClassVar[int]
    NEXT_READER_COUNT_FIELD_NUMBER: _ClassVar[int]
    PROCESS_COUNT_FIELD_NUMBER: _ClassVar[int]
    PROCESS_FIELD_NUMBER: _ClassVar[int]
    load_source: int
    load_source_count: int
    load_stored_fields: int
    load_stored_fields_count: int
    next_reader: int
    next_reader_count: int
    process_count: int
    process: int
    def __init__(self, load_source: _Optional[int] = ..., load_source_count: _Optional[int] = ..., load_stored_fields: _Optional[int] = ..., load_stored_fields_count: _Optional[int] = ..., next_reader: _Optional[int] = ..., next_reader_count: _Optional[int] = ..., process_count: _Optional[int] = ..., process: _Optional[int] = ...) -> None: ...

class AggregationProfileDebug(_message.Message):
    __slots__ = ("segments_with_multi_valued_ords", "collection_strategy", "segments_with_single_valued_ords", "total_buckets", "built_buckets", "result_strategy", "has_filter", "delegate", "delegate_debug", "chars_fetched", "extract_count", "extract_ns", "values_fetched", "collect_analyzed_ns", "collect_analyzed_count", "surviving_buckets", "ordinals_collectors_used", "ordinals_collectors_overhead_too_high", "string_hashing_collectors_used", "numeric_collectors_used", "empty_collectors_used", "deferred_aggregators", "map_reducer")
    SEGMENTS_WITH_MULTI_VALUED_ORDS_FIELD_NUMBER: _ClassVar[int]
    COLLECTION_STRATEGY_FIELD_NUMBER: _ClassVar[int]
    SEGMENTS_WITH_SINGLE_VALUED_ORDS_FIELD_NUMBER: _ClassVar[int]
    TOTAL_BUCKETS_FIELD_NUMBER: _ClassVar[int]
    BUILT_BUCKETS_FIELD_NUMBER: _ClassVar[int]
    RESULT_STRATEGY_FIELD_NUMBER: _ClassVar[int]
    HAS_FILTER_FIELD_NUMBER: _ClassVar[int]
    DELEGATE_FIELD_NUMBER: _ClassVar[int]
    DELEGATE_DEBUG_FIELD_NUMBER: _ClassVar[int]
    CHARS_FETCHED_FIELD_NUMBER: _ClassVar[int]
    EXTRACT_COUNT_FIELD_NUMBER: _ClassVar[int]
    EXTRACT_NS_FIELD_NUMBER: _ClassVar[int]
    VALUES_FETCHED_FIELD_NUMBER: _ClassVar[int]
    COLLECT_ANALYZED_NS_FIELD_NUMBER: _ClassVar[int]
    COLLECT_ANALYZED_COUNT_FIELD_NUMBER: _ClassVar[int]
    SURVIVING_BUCKETS_FIELD_NUMBER: _ClassVar[int]
    ORDINALS_COLLECTORS_USED_FIELD_NUMBER: _ClassVar[int]
    ORDINALS_COLLECTORS_OVERHEAD_TOO_HIGH_FIELD_NUMBER: _ClassVar[int]
    STRING_HASHING_COLLECTORS_USED_FIELD_NUMBER: _ClassVar[int]
    NUMERIC_COLLECTORS_USED_FIELD_NUMBER: _ClassVar[int]
    EMPTY_COLLECTORS_USED_FIELD_NUMBER: _ClassVar[int]
    DEFERRED_AGGREGATORS_FIELD_NUMBER: _ClassVar[int]
    MAP_REDUCER_FIELD_NUMBER: _ClassVar[int]
    segments_with_multi_valued_ords: int
    collection_strategy: str
    segments_with_single_valued_ords: int
    total_buckets: int
    built_buckets: int
    result_strategy: str
    has_filter: bool
    delegate: str
    delegate_debug: AggregationProfileDelegateDebug
    chars_fetched: int
    extract_count: int
    extract_ns: int
    values_fetched: int
    collect_analyzed_ns: int
    collect_analyzed_count: int
    surviving_buckets: int
    ordinals_collectors_used: int
    ordinals_collectors_overhead_too_high: int
    string_hashing_collectors_used: int
    numeric_collectors_used: int
    empty_collectors_used: int
    deferred_aggregators: _containers.RepeatedScalarFieldContainer[str]
    map_reducer: str
    def __init__(self, segments_with_multi_valued_ords: _Optional[int] = ..., collection_strategy: _Optional[str] = ..., segments_with_single_valued_ords: _Optional[int] = ..., total_buckets: _Optional[int] = ..., built_buckets: _Optional[int] = ..., result_strategy: _Optional[str] = ..., has_filter: bool = ..., delegate: _Optional[str] = ..., delegate_debug: _Optional[_Union[AggregationProfileDelegateDebug, _Mapping]] = ..., chars_fetched: _Optional[int] = ..., extract_count: _Optional[int] = ..., extract_ns: _Optional[int] = ..., values_fetched: _Optional[int] = ..., collect_analyzed_ns: _Optional[int] = ..., collect_analyzed_count: _Optional[int] = ..., surviving_buckets: _Optional[int] = ..., ordinals_collectors_used: _Optional[int] = ..., ordinals_collectors_overhead_too_high: _Optional[int] = ..., string_hashing_collectors_used: _Optional[int] = ..., numeric_collectors_used: _Optional[int] = ..., empty_collectors_used: _Optional[int] = ..., deferred_aggregators: _Optional[_Iterable[str]] = ..., map_reducer: _Optional[str] = ...) -> None: ...

class AggregationProfileDelegateDebug(_message.Message):
    __slots__ = ("segments_with_doc_count_field", "segments_with_deleted_docs", "filters", "segments_counted", "segments_collected")
    SEGMENTS_WITH_DOC_COUNT_FIELD_FIELD_NUMBER: _ClassVar[int]
    SEGMENTS_WITH_DELETED_DOCS_FIELD_NUMBER: _ClassVar[int]
    FILTERS_FIELD_NUMBER: _ClassVar[int]
    SEGMENTS_COUNTED_FIELD_NUMBER: _ClassVar[int]
    SEGMENTS_COLLECTED_FIELD_NUMBER: _ClassVar[int]
    segments_with_doc_count_field: int
    segments_with_deleted_docs: int
    filters: _containers.RepeatedCompositeFieldContainer[AggregationProfileDelegateDebugFilter]
    segments_counted: int
    segments_collected: int
    def __init__(self, segments_with_doc_count_field: _Optional[int] = ..., segments_with_deleted_docs: _Optional[int] = ..., filters: _Optional[_Iterable[_Union[AggregationProfileDelegateDebugFilter, _Mapping]]] = ..., segments_counted: _Optional[int] = ..., segments_collected: _Optional[int] = ...) -> None: ...

class AggregationProfileDelegateDebugFilter(_message.Message):
    __slots__ = ("results_from_metadata", "query", "specialized_for", "segments_counted_in_constant_time")
    RESULTS_FROM_METADATA_FIELD_NUMBER: _ClassVar[int]
    QUERY_FIELD_NUMBER: _ClassVar[int]
    SPECIALIZED_FOR_FIELD_NUMBER: _ClassVar[int]
    SEGMENTS_COUNTED_IN_CONSTANT_TIME_FIELD_NUMBER: _ClassVar[int]
    results_from_metadata: int
    query: str
    specialized_for: str
    segments_counted_in_constant_time: int
    def __init__(self, results_from_metadata: _Optional[int] = ..., query: _Optional[str] = ..., specialized_for: _Optional[str] = ..., segments_counted_in_constant_time: _Optional[int] = ...) -> None: ...

class Explanation(_message.Message):
    __slots__ = ("description", "details", "value")
    DESCRIPTION_FIELD_NUMBER: _ClassVar[int]
    DETAILS_FIELD_NUMBER: _ClassVar[int]
    VALUE_FIELD_NUMBER: _ClassVar[int]
    description: str
    details: _containers.RepeatedCompositeFieldContainer[Explanation]
    value: float
    def __init__(self, description: _Optional[str] = ..., details: _Optional[_Iterable[_Union[Explanation, _Mapping]]] = ..., value: _Optional[float] = ...) -> None: ...

class NestedIdentity(_message.Message):
    __slots__ = ("field", "offset", "x_nested")
    FIELD_FIELD_NUMBER: _ClassVar[int]
    OFFSET_FIELD_NUMBER: _ClassVar[int]
    X_NESTED_FIELD_NUMBER: _ClassVar[int]
    field: str
    offset: int
    x_nested: NestedIdentity
    def __init__(self, field: _Optional[str] = ..., offset: _Optional[int] = ..., x_nested: _Optional[_Union[NestedIdentity, _Mapping]] = ...) -> None: ...

class BulkRequest(_message.Message):
    __slots__ = ("index", "x_source", "x_source_excludes", "x_source_includes", "pipeline", "refresh", "require_alias", "routing", "timeout", "type", "wait_for_active_shards", "bulk_request_body", "global_params")
    INDEX_FIELD_NUMBER: _ClassVar[int]
    X_SOURCE_FIELD_NUMBER: _ClassVar[int]
    X_SOURCE_EXCLUDES_FIELD_NUMBER: _ClassVar[int]
    X_SOURCE_INCLUDES_FIELD_NUMBER: _ClassVar[int]
    PIPELINE_FIELD_NUMBER: _ClassVar[int]
    REFRESH_FIELD_NUMBER: _ClassVar[int]
    REQUIRE_ALIAS_FIELD_NUMBER: _ClassVar[int]
    ROUTING_FIELD_NUMBER: _ClassVar[int]
    TIMEOUT_FIELD_NUMBER: _ClassVar[int]
    TYPE_FIELD_NUMBER: _ClassVar[int]
    WAIT_FOR_ACTIVE_SHARDS_FIELD_NUMBER: _ClassVar[int]
    BULK_REQUEST_BODY_FIELD_NUMBER: _ClassVar[int]
    GLOBAL_PARAMS_FIELD_NUMBER: _ClassVar[int]
    index: str
    x_source: SourceConfigParam
    x_source_excludes: _containers.RepeatedScalarFieldContainer[str]
    x_source_includes: _containers.RepeatedScalarFieldContainer[str]
    pipeline: str
    refresh: Refresh
    require_alias: bool
    routing: str
    timeout: str
    type: str
    wait_for_active_shards: WaitForActiveShards
    bulk_request_body: _containers.RepeatedCompositeFieldContainer[BulkRequestBody]
    global_params: GlobalParams
    def __init__(self, index: _Optional[str] = ..., x_source: _Optional[_Union[SourceConfigParam, _Mapping]] = ..., x_source_excludes: _Optional[_Iterable[str]] = ..., x_source_includes: _Optional[_Iterable[str]] = ..., pipeline: _Optional[str] = ..., refresh: _Optional[_Union[Refresh, str]] = ..., require_alias: bool = ..., routing: _Optional[str] = ..., timeout: _Optional[str] = ..., type: _Optional[str] = ..., wait_for_active_shards: _Optional[_Union[WaitForActiveShards, _Mapping]] = ..., bulk_request_body: _Optional[_Iterable[_Union[BulkRequestBody, _Mapping]]] = ..., global_params: _Optional[_Union[GlobalParams, _Mapping]] = ...) -> None: ...

class BulkRequestBody(_message.Message):
    __slots__ = ("operation_container", "update_action", "object", "extra_field_values")
    class ExtraFieldValuesEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: BinaryFieldValue
        def __init__(self, key: _Optional[str] = ..., value: _Optional[_Union[BinaryFieldValue, _Mapping]] = ...) -> None: ...
    OPERATION_CONTAINER_FIELD_NUMBER: _ClassVar[int]
    UPDATE_ACTION_FIELD_NUMBER: _ClassVar[int]
    OBJECT_FIELD_NUMBER: _ClassVar[int]
    EXTRA_FIELD_VALUES_FIELD_NUMBER: _ClassVar[int]
    operation_container: OperationContainer
    update_action: UpdateAction
    object: bytes
    extra_field_values: _containers.MessageMap[str, BinaryFieldValue]
    def __init__(self, operation_container: _Optional[_Union[OperationContainer, _Mapping]] = ..., update_action: _Optional[_Union[UpdateAction, _Mapping]] = ..., object: _Optional[bytes] = ..., extra_field_values: _Optional[_Mapping[str, BinaryFieldValue]] = ...) -> None: ...

class OperationContainer(_message.Message):
    __slots__ = ("index", "create", "update", "delete")
    INDEX_FIELD_NUMBER: _ClassVar[int]
    CREATE_FIELD_NUMBER: _ClassVar[int]
    UPDATE_FIELD_NUMBER: _ClassVar[int]
    DELETE_FIELD_NUMBER: _ClassVar[int]
    index: IndexOperation
    create: WriteOperation
    update: UpdateOperation
    delete: DeleteOperation
    def __init__(self, index: _Optional[_Union[IndexOperation, _Mapping]] = ..., create: _Optional[_Union[WriteOperation, _Mapping]] = ..., update: _Optional[_Union[UpdateOperation, _Mapping]] = ..., delete: _Optional[_Union[DeleteOperation, _Mapping]] = ...) -> None: ...

class UpdateAction(_message.Message):
    __slots__ = ("detect_noop", "doc", "doc_as_upsert", "script", "scripted_upsert", "upsert", "x_source")
    DETECT_NOOP_FIELD_NUMBER: _ClassVar[int]
    DOC_FIELD_NUMBER: _ClassVar[int]
    DOC_AS_UPSERT_FIELD_NUMBER: _ClassVar[int]
    SCRIPT_FIELD_NUMBER: _ClassVar[int]
    SCRIPTED_UPSERT_FIELD_NUMBER: _ClassVar[int]
    UPSERT_FIELD_NUMBER: _ClassVar[int]
    X_SOURCE_FIELD_NUMBER: _ClassVar[int]
    detect_noop: bool
    doc: bytes
    doc_as_upsert: bool
    script: Script
    scripted_upsert: bool
    upsert: bytes
    x_source: SourceConfig
    def __init__(self, detect_noop: bool = ..., doc: _Optional[bytes] = ..., doc_as_upsert: bool = ..., script: _Optional[_Union[Script, _Mapping]] = ..., scripted_upsert: bool = ..., upsert: _Optional[bytes] = ..., x_source: _Optional[_Union[SourceConfig, _Mapping]] = ...) -> None: ...

class IndexOperation(_message.Message):
    __slots__ = ("x_id", "x_index", "routing", "if_primary_term", "if_seq_no", "op_type", "version", "version_type", "pipeline", "require_alias")
    X_ID_FIELD_NUMBER: _ClassVar[int]
    X_INDEX_FIELD_NUMBER: _ClassVar[int]
    ROUTING_FIELD_NUMBER: _ClassVar[int]
    IF_PRIMARY_TERM_FIELD_NUMBER: _ClassVar[int]
    IF_SEQ_NO_FIELD_NUMBER: _ClassVar[int]
    OP_TYPE_FIELD_NUMBER: _ClassVar[int]
    VERSION_FIELD_NUMBER: _ClassVar[int]
    VERSION_TYPE_FIELD_NUMBER: _ClassVar[int]
    PIPELINE_FIELD_NUMBER: _ClassVar[int]
    REQUIRE_ALIAS_FIELD_NUMBER: _ClassVar[int]
    x_id: str
    x_index: str
    routing: str
    if_primary_term: int
    if_seq_no: int
    op_type: OpType
    version: int
    version_type: VersionType
    pipeline: str
    require_alias: bool
    def __init__(self, x_id: _Optional[str] = ..., x_index: _Optional[str] = ..., routing: _Optional[str] = ..., if_primary_term: _Optional[int] = ..., if_seq_no: _Optional[int] = ..., op_type: _Optional[_Union[OpType, str]] = ..., version: _Optional[int] = ..., version_type: _Optional[_Union[VersionType, str]] = ..., pipeline: _Optional[str] = ..., require_alias: bool = ...) -> None: ...

class WriteOperation(_message.Message):
    __slots__ = ("routing", "x_id", "x_index", "pipeline", "require_alias")
    ROUTING_FIELD_NUMBER: _ClassVar[int]
    X_ID_FIELD_NUMBER: _ClassVar[int]
    X_INDEX_FIELD_NUMBER: _ClassVar[int]
    PIPELINE_FIELD_NUMBER: _ClassVar[int]
    REQUIRE_ALIAS_FIELD_NUMBER: _ClassVar[int]
    routing: str
    x_id: str
    x_index: str
    pipeline: str
    require_alias: bool
    def __init__(self, routing: _Optional[str] = ..., x_id: _Optional[str] = ..., x_index: _Optional[str] = ..., pipeline: _Optional[str] = ..., require_alias: bool = ...) -> None: ...

class UpdateOperation(_message.Message):
    __slots__ = ("x_id", "x_index", "routing", "if_primary_term", "if_seq_no", "require_alias", "retry_on_conflict")
    X_ID_FIELD_NUMBER: _ClassVar[int]
    X_INDEX_FIELD_NUMBER: _ClassVar[int]
    ROUTING_FIELD_NUMBER: _ClassVar[int]
    IF_PRIMARY_TERM_FIELD_NUMBER: _ClassVar[int]
    IF_SEQ_NO_FIELD_NUMBER: _ClassVar[int]
    REQUIRE_ALIAS_FIELD_NUMBER: _ClassVar[int]
    RETRY_ON_CONFLICT_FIELD_NUMBER: _ClassVar[int]
    x_id: str
    x_index: str
    routing: str
    if_primary_term: int
    if_seq_no: int
    require_alias: bool
    retry_on_conflict: int
    def __init__(self, x_id: _Optional[str] = ..., x_index: _Optional[str] = ..., routing: _Optional[str] = ..., if_primary_term: _Optional[int] = ..., if_seq_no: _Optional[int] = ..., require_alias: bool = ..., retry_on_conflict: _Optional[int] = ...) -> None: ...

class DeleteOperation(_message.Message):
    __slots__ = ("x_id", "x_index", "routing", "if_primary_term", "if_seq_no", "version", "version_type")
    X_ID_FIELD_NUMBER: _ClassVar[int]
    X_INDEX_FIELD_NUMBER: _ClassVar[int]
    ROUTING_FIELD_NUMBER: _ClassVar[int]
    IF_PRIMARY_TERM_FIELD_NUMBER: _ClassVar[int]
    IF_SEQ_NO_FIELD_NUMBER: _ClassVar[int]
    VERSION_FIELD_NUMBER: _ClassVar[int]
    VERSION_TYPE_FIELD_NUMBER: _ClassVar[int]
    x_id: str
    x_index: str
    routing: str
    if_primary_term: int
    if_seq_no: int
    version: int
    version_type: VersionType
    def __init__(self, x_id: _Optional[str] = ..., x_index: _Optional[str] = ..., routing: _Optional[str] = ..., if_primary_term: _Optional[int] = ..., if_seq_no: _Optional[int] = ..., version: _Optional[int] = ..., version_type: _Optional[_Union[VersionType, str]] = ...) -> None: ...

class BulkResponse(_message.Message):
    __slots__ = ("errors", "items", "took", "ingest_took")
    ERRORS_FIELD_NUMBER: _ClassVar[int]
    ITEMS_FIELD_NUMBER: _ClassVar[int]
    TOOK_FIELD_NUMBER: _ClassVar[int]
    INGEST_TOOK_FIELD_NUMBER: _ClassVar[int]
    errors: bool
    items: _containers.RepeatedCompositeFieldContainer[Item]
    took: int
    ingest_took: int
    def __init__(self, errors: bool = ..., items: _Optional[_Iterable[_Union[Item, _Mapping]]] = ..., took: _Optional[int] = ..., ingest_took: _Optional[int] = ...) -> None: ...

class Item(_message.Message):
    __slots__ = ("create", "delete", "index", "update")
    CREATE_FIELD_NUMBER: _ClassVar[int]
    DELETE_FIELD_NUMBER: _ClassVar[int]
    INDEX_FIELD_NUMBER: _ClassVar[int]
    UPDATE_FIELD_NUMBER: _ClassVar[int]
    create: ResponseItem
    delete: ResponseItem
    index: ResponseItem
    update: ResponseItem
    def __init__(self, create: _Optional[_Union[ResponseItem, _Mapping]] = ..., delete: _Optional[_Union[ResponseItem, _Mapping]] = ..., index: _Optional[_Union[ResponseItem, _Mapping]] = ..., update: _Optional[_Union[ResponseItem, _Mapping]] = ...) -> None: ...

class ResponseItem(_message.Message):
    __slots__ = ("x_index", "status", "x_type", "x_id", "error", "x_primary_term", "result", "x_seq_no", "x_shards", "x_version", "forced_refresh", "get")
    X_INDEX_FIELD_NUMBER: _ClassVar[int]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    X_TYPE_FIELD_NUMBER: _ClassVar[int]
    X_ID_FIELD_NUMBER: _ClassVar[int]
    ERROR_FIELD_NUMBER: _ClassVar[int]
    X_PRIMARY_TERM_FIELD_NUMBER: _ClassVar[int]
    RESULT_FIELD_NUMBER: _ClassVar[int]
    X_SEQ_NO_FIELD_NUMBER: _ClassVar[int]
    X_SHARDS_FIELD_NUMBER: _ClassVar[int]
    X_VERSION_FIELD_NUMBER: _ClassVar[int]
    FORCED_REFRESH_FIELD_NUMBER: _ClassVar[int]
    GET_FIELD_NUMBER: _ClassVar[int]
    x_index: str
    status: int
    x_type: str
    x_id: str
    error: ErrorCause
    x_primary_term: int
    result: str
    x_seq_no: int
    x_shards: ShardInfo
    x_version: int
    forced_refresh: bool
    get: InlineGetDictUserDefined
    def __init__(self, x_index: _Optional[str] = ..., status: _Optional[int] = ..., x_type: _Optional[str] = ..., x_id: _Optional[str] = ..., error: _Optional[_Union[ErrorCause, _Mapping]] = ..., x_primary_term: _Optional[int] = ..., result: _Optional[str] = ..., x_seq_no: _Optional[int] = ..., x_shards: _Optional[_Union[ShardInfo, _Mapping]] = ..., x_version: _Optional[int] = ..., forced_refresh: bool = ..., get: _Optional[_Union[InlineGetDictUserDefined, _Mapping]] = ...) -> None: ...

class InlineGetDictUserDefined(_message.Message):
    __slots__ = ("metadata_fields", "fields", "found", "x_seq_no", "x_primary_term", "x_routing", "x_source")
    METADATA_FIELDS_FIELD_NUMBER: _ClassVar[int]
    FIELDS_FIELD_NUMBER: _ClassVar[int]
    FOUND_FIELD_NUMBER: _ClassVar[int]
    X_SEQ_NO_FIELD_NUMBER: _ClassVar[int]
    X_PRIMARY_TERM_FIELD_NUMBER: _ClassVar[int]
    X_ROUTING_FIELD_NUMBER: _ClassVar[int]
    X_SOURCE_FIELD_NUMBER: _ClassVar[int]
    metadata_fields: ObjectMap
    fields: ObjectMap
    found: bool
    x_seq_no: int
    x_primary_term: int
    x_routing: str
    x_source: bytes
    def __init__(self, metadata_fields: _Optional[_Union[ObjectMap, _Mapping]] = ..., fields: _Optional[_Union[ObjectMap, _Mapping]] = ..., found: bool = ..., x_seq_no: _Optional[int] = ..., x_primary_term: _Optional[int] = ..., x_routing: _Optional[str] = ..., x_source: _Optional[bytes] = ...) -> None: ...

class GlobalParams(_message.Message):
    __slots__ = ("human", "error_trace", "filter_path")
    HUMAN_FIELD_NUMBER: _ClassVar[int]
    ERROR_TRACE_FIELD_NUMBER: _ClassVar[int]
    FILTER_PATH_FIELD_NUMBER: _ClassVar[int]
    human: bool
    error_trace: bool
    filter_path: _containers.RepeatedScalarFieldContainer[str]
    def __init__(self, human: bool = ..., error_trace: bool = ..., filter_path: _Optional[_Iterable[str]] = ...) -> None: ...

class WaitForActiveShards(_message.Message):
    __slots__ = ("count", "option")
    COUNT_FIELD_NUMBER: _ClassVar[int]
    OPTION_FIELD_NUMBER: _ClassVar[int]
    count: int
    option: WaitForActiveShardOptions
    def __init__(self, count: _Optional[int] = ..., option: _Optional[_Union[WaitForActiveShardOptions, str]] = ...) -> None: ...

class Script(_message.Message):
    __slots__ = ("inline", "stored")
    INLINE_FIELD_NUMBER: _ClassVar[int]
    STORED_FIELD_NUMBER: _ClassVar[int]
    inline: InlineScript
    stored: StoredScriptId
    def __init__(self, inline: _Optional[_Union[InlineScript, _Mapping]] = ..., stored: _Optional[_Union[StoredScriptId, _Mapping]] = ...) -> None: ...

class InlineScript(_message.Message):
    __slots__ = ("params", "lang", "options", "source")
    class OptionsEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: str
        def __init__(self, key: _Optional[str] = ..., value: _Optional[str] = ...) -> None: ...
    PARAMS_FIELD_NUMBER: _ClassVar[int]
    LANG_FIELD_NUMBER: _ClassVar[int]
    OPTIONS_FIELD_NUMBER: _ClassVar[int]
    SOURCE_FIELD_NUMBER: _ClassVar[int]
    params: ObjectMap
    lang: ScriptLanguage
    options: _containers.ScalarMap[str, str]
    source: str
    def __init__(self, params: _Optional[_Union[ObjectMap, _Mapping]] = ..., lang: _Optional[_Union[ScriptLanguage, _Mapping]] = ..., options: _Optional[_Mapping[str, str]] = ..., source: _Optional[str] = ...) -> None: ...

class ScriptLanguage(_message.Message):
    __slots__ = ("builtin", "custom")
    BUILTIN_FIELD_NUMBER: _ClassVar[int]
    CUSTOM_FIELD_NUMBER: _ClassVar[int]
    builtin: BuiltinScriptLanguage
    custom: str
    def __init__(self, builtin: _Optional[_Union[BuiltinScriptLanguage, str]] = ..., custom: _Optional[str] = ...) -> None: ...

class StoredScriptId(_message.Message):
    __slots__ = ("params", "id")
    PARAMS_FIELD_NUMBER: _ClassVar[int]
    ID_FIELD_NUMBER: _ClassVar[int]
    params: ObjectMap
    id: str
    def __init__(self, params: _Optional[_Union[ObjectMap, _Mapping]] = ..., id: _Optional[str] = ...) -> None: ...

class GeoLocation(_message.Message):
    __slots__ = ("latlon", "geohash", "coords", "text")
    LATLON_FIELD_NUMBER: _ClassVar[int]
    GEOHASH_FIELD_NUMBER: _ClassVar[int]
    COORDS_FIELD_NUMBER: _ClassVar[int]
    TEXT_FIELD_NUMBER: _ClassVar[int]
    latlon: LatLonGeoLocation
    geohash: GeoHashLocation
    coords: DoubleArray
    text: str
    def __init__(self, latlon: _Optional[_Union[LatLonGeoLocation, _Mapping]] = ..., geohash: _Optional[_Union[GeoHashLocation, _Mapping]] = ..., coords: _Optional[_Union[DoubleArray, _Mapping]] = ..., text: _Optional[str] = ...) -> None: ...

class DoubleArray(_message.Message):
    __slots__ = ("double_array",)
    DOUBLE_ARRAY_FIELD_NUMBER: _ClassVar[int]
    double_array: _containers.RepeatedScalarFieldContainer[float]
    def __init__(self, double_array: _Optional[_Iterable[float]] = ...) -> None: ...

class LatLonGeoLocation(_message.Message):
    __slots__ = ("lat", "lon")
    LAT_FIELD_NUMBER: _ClassVar[int]
    LON_FIELD_NUMBER: _ClassVar[int]
    lat: float
    lon: float
    def __init__(self, lat: _Optional[float] = ..., lon: _Optional[float] = ...) -> None: ...

class GeoHashLocation(_message.Message):
    __slots__ = ("geohash",)
    GEOHASH_FIELD_NUMBER: _ClassVar[int]
    geohash: str
    def __init__(self, geohash: _Optional[str] = ...) -> None: ...

class SourceConfigParam(_message.Message):
    __slots__ = ("fetch", "fields")
    FETCH_FIELD_NUMBER: _ClassVar[int]
    FIELDS_FIELD_NUMBER: _ClassVar[int]
    fetch: bool
    fields: StringArray
    def __init__(self, fetch: bool = ..., fields: _Optional[_Union[StringArray, _Mapping]] = ...) -> None: ...

class StringArray(_message.Message):
    __slots__ = ("string_array",)
    STRING_ARRAY_FIELD_NUMBER: _ClassVar[int]
    string_array: _containers.RepeatedScalarFieldContainer[str]
    def __init__(self, string_array: _Optional[_Iterable[str]] = ...) -> None: ...

class SourceConfig(_message.Message):
    __slots__ = ("fetch", "filter")
    FETCH_FIELD_NUMBER: _ClassVar[int]
    FILTER_FIELD_NUMBER: _ClassVar[int]
    fetch: bool
    filter: SourceFilter
    def __init__(self, fetch: bool = ..., filter: _Optional[_Union[SourceFilter, _Mapping]] = ...) -> None: ...

class SourceFilter(_message.Message):
    __slots__ = ("excludes", "includes")
    EXCLUDES_FIELD_NUMBER: _ClassVar[int]
    INCLUDES_FIELD_NUMBER: _ClassVar[int]
    excludes: _containers.RepeatedScalarFieldContainer[str]
    includes: _containers.RepeatedScalarFieldContainer[str]
    def __init__(self, excludes: _Optional[_Iterable[str]] = ..., includes: _Optional[_Iterable[str]] = ...) -> None: ...

class ErrorCause(_message.Message):
    __slots__ = ("type", "reason", "stack_trace", "caused_by", "root_cause", "suppressed", "metadata", "header")
    class HeaderEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: StringArray
        def __init__(self, key: _Optional[str] = ..., value: _Optional[_Union[StringArray, _Mapping]] = ...) -> None: ...
    TYPE_FIELD_NUMBER: _ClassVar[int]
    REASON_FIELD_NUMBER: _ClassVar[int]
    STACK_TRACE_FIELD_NUMBER: _ClassVar[int]
    CAUSED_BY_FIELD_NUMBER: _ClassVar[int]
    ROOT_CAUSE_FIELD_NUMBER: _ClassVar[int]
    SUPPRESSED_FIELD_NUMBER: _ClassVar[int]
    METADATA_FIELD_NUMBER: _ClassVar[int]
    HEADER_FIELD_NUMBER: _ClassVar[int]
    type: str
    reason: str
    stack_trace: str
    caused_by: ErrorCause
    root_cause: _containers.RepeatedCompositeFieldContainer[ErrorCause]
    suppressed: _containers.RepeatedCompositeFieldContainer[ErrorCause]
    metadata: ObjectMap
    header: _containers.MessageMap[str, StringArray]
    def __init__(self, type: _Optional[str] = ..., reason: _Optional[str] = ..., stack_trace: _Optional[str] = ..., caused_by: _Optional[_Union[ErrorCause, _Mapping]] = ..., root_cause: _Optional[_Iterable[_Union[ErrorCause, _Mapping]]] = ..., suppressed: _Optional[_Iterable[_Union[ErrorCause, _Mapping]]] = ..., metadata: _Optional[_Union[ObjectMap, _Mapping]] = ..., header: _Optional[_Mapping[str, StringArray]] = ...) -> None: ...

class ShardStatistics(_message.Message):
    __slots__ = ("failed", "successful", "total", "failures", "skipped", "failures_2")
    FAILED_FIELD_NUMBER: _ClassVar[int]
    SUCCESSFUL_FIELD_NUMBER: _ClassVar[int]
    TOTAL_FIELD_NUMBER: _ClassVar[int]
    FAILURES_FIELD_NUMBER: _ClassVar[int]
    SKIPPED_FIELD_NUMBER: _ClassVar[int]
    FAILURES_2_FIELD_NUMBER: _ClassVar[int]
    failed: int
    successful: int
    total: int
    failures: _containers.RepeatedCompositeFieldContainer[ShardFailure]
    skipped: int
    failures_2: _containers.RepeatedCompositeFieldContainer[ShardSearchFailure]
    def __init__(self, failed: _Optional[int] = ..., successful: _Optional[int] = ..., total: _Optional[int] = ..., failures: _Optional[_Iterable[_Union[ShardFailure, _Mapping]]] = ..., skipped: _Optional[int] = ..., failures_2: _Optional[_Iterable[_Union[ShardSearchFailure, _Mapping]]] = ...) -> None: ...

class ShardInfo(_message.Message):
    __slots__ = ("failed", "successful", "total", "failures")
    FAILED_FIELD_NUMBER: _ClassVar[int]
    SUCCESSFUL_FIELD_NUMBER: _ClassVar[int]
    TOTAL_FIELD_NUMBER: _ClassVar[int]
    FAILURES_FIELD_NUMBER: _ClassVar[int]
    failed: int
    successful: int
    total: int
    failures: _containers.RepeatedCompositeFieldContainer[ShardFailure]
    def __init__(self, failed: _Optional[int] = ..., successful: _Optional[int] = ..., total: _Optional[int] = ..., failures: _Optional[_Iterable[_Union[ShardFailure, _Mapping]]] = ...) -> None: ...

class ShardFailure(_message.Message):
    __slots__ = ("index", "node", "reason", "shard", "status", "primary")
    INDEX_FIELD_NUMBER: _ClassVar[int]
    NODE_FIELD_NUMBER: _ClassVar[int]
    REASON_FIELD_NUMBER: _ClassVar[int]
    SHARD_FIELD_NUMBER: _ClassVar[int]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    PRIMARY_FIELD_NUMBER: _ClassVar[int]
    index: str
    node: str
    reason: ErrorCause
    shard: int
    status: str
    primary: bool
    def __init__(self, index: _Optional[str] = ..., node: _Optional[str] = ..., reason: _Optional[_Union[ErrorCause, _Mapping]] = ..., shard: _Optional[int] = ..., status: _Optional[str] = ..., primary: bool = ...) -> None: ...

class QueryContainer(_message.Message):
    __slots__ = ("bool", "constant_score", "function_score", "exists", "fuzzy", "ids", "prefix", "range", "regexp", "term", "terms", "terms_set", "wildcard", "match", "match_bool_prefix", "match_phrase", "match_phrase_prefix", "multi_match", "knn", "match_all", "match_none", "nested", "geo_distance", "geo_bounding_box", "script", "hybrid", "sltr")
    BOOL_FIELD_NUMBER: _ClassVar[int]
    CONSTANT_SCORE_FIELD_NUMBER: _ClassVar[int]
    FUNCTION_SCORE_FIELD_NUMBER: _ClassVar[int]
    EXISTS_FIELD_NUMBER: _ClassVar[int]
    FUZZY_FIELD_NUMBER: _ClassVar[int]
    IDS_FIELD_NUMBER: _ClassVar[int]
    PREFIX_FIELD_NUMBER: _ClassVar[int]
    RANGE_FIELD_NUMBER: _ClassVar[int]
    REGEXP_FIELD_NUMBER: _ClassVar[int]
    TERM_FIELD_NUMBER: _ClassVar[int]
    TERMS_FIELD_NUMBER: _ClassVar[int]
    TERMS_SET_FIELD_NUMBER: _ClassVar[int]
    WILDCARD_FIELD_NUMBER: _ClassVar[int]
    MATCH_FIELD_NUMBER: _ClassVar[int]
    MATCH_BOOL_PREFIX_FIELD_NUMBER: _ClassVar[int]
    MATCH_PHRASE_FIELD_NUMBER: _ClassVar[int]
    MATCH_PHRASE_PREFIX_FIELD_NUMBER: _ClassVar[int]
    MULTI_MATCH_FIELD_NUMBER: _ClassVar[int]
    KNN_FIELD_NUMBER: _ClassVar[int]
    MATCH_ALL_FIELD_NUMBER: _ClassVar[int]
    MATCH_NONE_FIELD_NUMBER: _ClassVar[int]
    NESTED_FIELD_NUMBER: _ClassVar[int]
    GEO_DISTANCE_FIELD_NUMBER: _ClassVar[int]
    GEO_BOUNDING_BOX_FIELD_NUMBER: _ClassVar[int]
    SCRIPT_FIELD_NUMBER: _ClassVar[int]
    HYBRID_FIELD_NUMBER: _ClassVar[int]
    SLTR_FIELD_NUMBER: _ClassVar[int]
    bool: BoolQuery
    constant_score: ConstantScoreQuery
    function_score: FunctionScoreQuery
    exists: ExistsQuery
    fuzzy: FuzzyQuery
    ids: IdsQuery
    prefix: PrefixQuery
    range: RangeQuery
    regexp: RegexpQuery
    term: TermQuery
    terms: TermsQuery
    terms_set: TermsSetQuery
    wildcard: WildcardQuery
    match: MatchQuery
    match_bool_prefix: MatchBoolPrefixQuery
    match_phrase: MatchPhraseQuery
    match_phrase_prefix: MatchPhrasePrefixQuery
    multi_match: MultiMatchQuery
    knn: KnnQuery
    match_all: MatchAllQuery
    match_none: MatchNoneQuery
    nested: NestedQuery
    geo_distance: GeoDistanceQuery
    geo_bounding_box: GeoBoundingBoxQuery
    script: ScriptQuery
    hybrid: HybridQuery
    sltr: StoredLtrQuery
    def __init__(self, bool: _Optional[_Union[BoolQuery, _Mapping]] = ..., constant_score: _Optional[_Union[ConstantScoreQuery, _Mapping]] = ..., function_score: _Optional[_Union[FunctionScoreQuery, _Mapping]] = ..., exists: _Optional[_Union[ExistsQuery, _Mapping]] = ..., fuzzy: _Optional[_Union[FuzzyQuery, _Mapping]] = ..., ids: _Optional[_Union[IdsQuery, _Mapping]] = ..., prefix: _Optional[_Union[PrefixQuery, _Mapping]] = ..., range: _Optional[_Union[RangeQuery, _Mapping]] = ..., regexp: _Optional[_Union[RegexpQuery, _Mapping]] = ..., term: _Optional[_Union[TermQuery, _Mapping]] = ..., terms: _Optional[_Union[TermsQuery, _Mapping]] = ..., terms_set: _Optional[_Union[TermsSetQuery, _Mapping]] = ..., wildcard: _Optional[_Union[WildcardQuery, _Mapping]] = ..., match: _Optional[_Union[MatchQuery, _Mapping]] = ..., match_bool_prefix: _Optional[_Union[MatchBoolPrefixQuery, _Mapping]] = ..., match_phrase: _Optional[_Union[MatchPhraseQuery, _Mapping]] = ..., match_phrase_prefix: _Optional[_Union[MatchPhrasePrefixQuery, _Mapping]] = ..., multi_match: _Optional[_Union[MultiMatchQuery, _Mapping]] = ..., knn: _Optional[_Union[KnnQuery, _Mapping]] = ..., match_all: _Optional[_Union[MatchAllQuery, _Mapping]] = ..., match_none: _Optional[_Union[MatchNoneQuery, _Mapping]] = ..., nested: _Optional[_Union[NestedQuery, _Mapping]] = ..., geo_distance: _Optional[_Union[GeoDistanceQuery, _Mapping]] = ..., geo_bounding_box: _Optional[_Union[GeoBoundingBoxQuery, _Mapping]] = ..., script: _Optional[_Union[ScriptQuery, _Mapping]] = ..., hybrid: _Optional[_Union[HybridQuery, _Mapping]] = ..., sltr: _Optional[_Union[StoredLtrQuery, _Mapping]] = ...) -> None: ...

class HybridQuery(_message.Message):
    __slots__ = ("boost", "x_name", "queries", "pagination_depth", "filter")
    BOOST_FIELD_NUMBER: _ClassVar[int]
    X_NAME_FIELD_NUMBER: _ClassVar[int]
    QUERIES_FIELD_NUMBER: _ClassVar[int]
    PAGINATION_DEPTH_FIELD_NUMBER: _ClassVar[int]
    FILTER_FIELD_NUMBER: _ClassVar[int]
    boost: float
    x_name: str
    queries: _containers.RepeatedCompositeFieldContainer[QueryContainer]
    pagination_depth: int
    filter: QueryContainer
    def __init__(self, boost: _Optional[float] = ..., x_name: _Optional[str] = ..., queries: _Optional[_Iterable[_Union[QueryContainer, _Mapping]]] = ..., pagination_depth: _Optional[int] = ..., filter: _Optional[_Union[QueryContainer, _Mapping]] = ...) -> None: ...

class ScriptQuery(_message.Message):
    __slots__ = ("script", "boost", "x_name")
    SCRIPT_FIELD_NUMBER: _ClassVar[int]
    BOOST_FIELD_NUMBER: _ClassVar[int]
    X_NAME_FIELD_NUMBER: _ClassVar[int]
    script: Script
    boost: float
    x_name: str
    def __init__(self, script: _Optional[_Union[Script, _Mapping]] = ..., boost: _Optional[float] = ..., x_name: _Optional[str] = ...) -> None: ...

class GeoBoundingBoxQuery(_message.Message):
    __slots__ = ("boost", "x_name", "type", "validation_method", "ignore_unmapped", "bounding_box")
    class BoundingBoxEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: GeoBounds
        def __init__(self, key: _Optional[str] = ..., value: _Optional[_Union[GeoBounds, _Mapping]] = ...) -> None: ...
    BOOST_FIELD_NUMBER: _ClassVar[int]
    X_NAME_FIELD_NUMBER: _ClassVar[int]
    TYPE_FIELD_NUMBER: _ClassVar[int]
    VALIDATION_METHOD_FIELD_NUMBER: _ClassVar[int]
    IGNORE_UNMAPPED_FIELD_NUMBER: _ClassVar[int]
    BOUNDING_BOX_FIELD_NUMBER: _ClassVar[int]
    boost: float
    x_name: str
    type: GeoExecution
    validation_method: GeoValidationMethod
    ignore_unmapped: bool
    bounding_box: _containers.MessageMap[str, GeoBounds]
    def __init__(self, boost: _Optional[float] = ..., x_name: _Optional[str] = ..., type: _Optional[_Union[GeoExecution, str]] = ..., validation_method: _Optional[_Union[GeoValidationMethod, str]] = ..., ignore_unmapped: bool = ..., bounding_box: _Optional[_Mapping[str, GeoBounds]] = ...) -> None: ...

class GeoBounds(_message.Message):
    __slots__ = ("coords", "tlbr", "trbl", "wkt")
    COORDS_FIELD_NUMBER: _ClassVar[int]
    TLBR_FIELD_NUMBER: _ClassVar[int]
    TRBL_FIELD_NUMBER: _ClassVar[int]
    WKT_FIELD_NUMBER: _ClassVar[int]
    coords: CoordsGeoBounds
    tlbr: TopLeftBottomRightGeoBounds
    trbl: TopRightBottomLeftGeoBounds
    wkt: WktGeoBounds
    def __init__(self, coords: _Optional[_Union[CoordsGeoBounds, _Mapping]] = ..., tlbr: _Optional[_Union[TopLeftBottomRightGeoBounds, _Mapping]] = ..., trbl: _Optional[_Union[TopRightBottomLeftGeoBounds, _Mapping]] = ..., wkt: _Optional[_Union[WktGeoBounds, _Mapping]] = ...) -> None: ...

class WktGeoBounds(_message.Message):
    __slots__ = ("wkt",)
    WKT_FIELD_NUMBER: _ClassVar[int]
    wkt: str
    def __init__(self, wkt: _Optional[str] = ...) -> None: ...

class CoordsGeoBounds(_message.Message):
    __slots__ = ("top", "bottom", "left", "right")
    TOP_FIELD_NUMBER: _ClassVar[int]
    BOTTOM_FIELD_NUMBER: _ClassVar[int]
    LEFT_FIELD_NUMBER: _ClassVar[int]
    RIGHT_FIELD_NUMBER: _ClassVar[int]
    top: float
    bottom: float
    left: float
    right: float
    def __init__(self, top: _Optional[float] = ..., bottom: _Optional[float] = ..., left: _Optional[float] = ..., right: _Optional[float] = ...) -> None: ...

class TopLeftBottomRightGeoBounds(_message.Message):
    __slots__ = ("top_left", "bottom_right")
    TOP_LEFT_FIELD_NUMBER: _ClassVar[int]
    BOTTOM_RIGHT_FIELD_NUMBER: _ClassVar[int]
    top_left: GeoLocation
    bottom_right: GeoLocation
    def __init__(self, top_left: _Optional[_Union[GeoLocation, _Mapping]] = ..., bottom_right: _Optional[_Union[GeoLocation, _Mapping]] = ...) -> None: ...

class TopRightBottomLeftGeoBounds(_message.Message):
    __slots__ = ("top_right", "bottom_left")
    TOP_RIGHT_FIELD_NUMBER: _ClassVar[int]
    BOTTOM_LEFT_FIELD_NUMBER: _ClassVar[int]
    top_right: GeoLocation
    bottom_left: GeoLocation
    def __init__(self, top_right: _Optional[_Union[GeoLocation, _Mapping]] = ..., bottom_left: _Optional[_Union[GeoLocation, _Mapping]] = ...) -> None: ...

class GeoDistanceQuery(_message.Message):
    __slots__ = ("distance", "boost", "x_name", "distance_type", "validation_method", "ignore_unmapped", "unit", "location")
    class LocationEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: GeoLocation
        def __init__(self, key: _Optional[str] = ..., value: _Optional[_Union[GeoLocation, _Mapping]] = ...) -> None: ...
    DISTANCE_FIELD_NUMBER: _ClassVar[int]
    BOOST_FIELD_NUMBER: _ClassVar[int]
    X_NAME_FIELD_NUMBER: _ClassVar[int]
    DISTANCE_TYPE_FIELD_NUMBER: _ClassVar[int]
    VALIDATION_METHOD_FIELD_NUMBER: _ClassVar[int]
    IGNORE_UNMAPPED_FIELD_NUMBER: _ClassVar[int]
    UNIT_FIELD_NUMBER: _ClassVar[int]
    LOCATION_FIELD_NUMBER: _ClassVar[int]
    distance: str
    boost: float
    x_name: str
    distance_type: GeoDistanceType
    validation_method: GeoValidationMethod
    ignore_unmapped: bool
    unit: DistanceUnit
    location: _containers.MessageMap[str, GeoLocation]
    def __init__(self, distance: _Optional[str] = ..., boost: _Optional[float] = ..., x_name: _Optional[str] = ..., distance_type: _Optional[_Union[GeoDistanceType, str]] = ..., validation_method: _Optional[_Union[GeoValidationMethod, str]] = ..., ignore_unmapped: bool = ..., unit: _Optional[_Union[DistanceUnit, str]] = ..., location: _Optional[_Mapping[str, GeoLocation]] = ...) -> None: ...

class TermsQuery(_message.Message):
    __slots__ = ("boost", "x_name", "value_type", "terms")
    class TermsEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: TermsQueryField
        def __init__(self, key: _Optional[str] = ..., value: _Optional[_Union[TermsQueryField, _Mapping]] = ...) -> None: ...
    BOOST_FIELD_NUMBER: _ClassVar[int]
    X_NAME_FIELD_NUMBER: _ClassVar[int]
    VALUE_TYPE_FIELD_NUMBER: _ClassVar[int]
    TERMS_FIELD_NUMBER: _ClassVar[int]
    boost: float
    x_name: str
    value_type: TermsQueryValueType
    terms: _containers.MessageMap[str, TermsQueryField]
    def __init__(self, boost: _Optional[float] = ..., x_name: _Optional[str] = ..., value_type: _Optional[_Union[TermsQueryValueType, str]] = ..., terms: _Optional[_Mapping[str, TermsQueryField]] = ...) -> None: ...

class NestedQuery(_message.Message):
    __slots__ = ("path", "query", "boost", "x_name", "ignore_unmapped", "inner_hits", "score_mode")
    PATH_FIELD_NUMBER: _ClassVar[int]
    QUERY_FIELD_NUMBER: _ClassVar[int]
    BOOST_FIELD_NUMBER: _ClassVar[int]
    X_NAME_FIELD_NUMBER: _ClassVar[int]
    IGNORE_UNMAPPED_FIELD_NUMBER: _ClassVar[int]
    INNER_HITS_FIELD_NUMBER: _ClassVar[int]
    SCORE_MODE_FIELD_NUMBER: _ClassVar[int]
    path: str
    query: QueryContainer
    boost: float
    x_name: str
    ignore_unmapped: bool
    inner_hits: InnerHits
    score_mode: ChildScoreMode
    def __init__(self, path: _Optional[str] = ..., query: _Optional[_Union[QueryContainer, _Mapping]] = ..., boost: _Optional[float] = ..., x_name: _Optional[str] = ..., ignore_unmapped: bool = ..., inner_hits: _Optional[_Union[InnerHits, _Mapping]] = ..., score_mode: _Optional[_Union[ChildScoreMode, str]] = ...) -> None: ...

class InnerHits(_message.Message):
    __slots__ = ("name", "size", "collapse", "docvalue_fields", "explain", "highlight", "ignore_unmapped", "script_fields", "seq_no_primary_term", "fields", "sort", "x_source", "stored_fields", "track_scores", "version")
    class ScriptFieldsEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: ScriptField
        def __init__(self, key: _Optional[str] = ..., value: _Optional[_Union[ScriptField, _Mapping]] = ...) -> None: ...
    NAME_FIELD_NUMBER: _ClassVar[int]
    SIZE_FIELD_NUMBER: _ClassVar[int]
    FROM_FIELD_NUMBER: _ClassVar[int]
    COLLAPSE_FIELD_NUMBER: _ClassVar[int]
    DOCVALUE_FIELDS_FIELD_NUMBER: _ClassVar[int]
    EXPLAIN_FIELD_NUMBER: _ClassVar[int]
    HIGHLIGHT_FIELD_NUMBER: _ClassVar[int]
    IGNORE_UNMAPPED_FIELD_NUMBER: _ClassVar[int]
    SCRIPT_FIELDS_FIELD_NUMBER: _ClassVar[int]
    SEQ_NO_PRIMARY_TERM_FIELD_NUMBER: _ClassVar[int]
    FIELDS_FIELD_NUMBER: _ClassVar[int]
    SORT_FIELD_NUMBER: _ClassVar[int]
    X_SOURCE_FIELD_NUMBER: _ClassVar[int]
    STORED_FIELDS_FIELD_NUMBER: _ClassVar[int]
    TRACK_SCORES_FIELD_NUMBER: _ClassVar[int]
    VERSION_FIELD_NUMBER: _ClassVar[int]
    name: str
    size: int
    collapse: FieldCollapse
    docvalue_fields: _containers.RepeatedCompositeFieldContainer[FieldAndFormat]
    explain: bool
    highlight: Highlight
    ignore_unmapped: bool
    script_fields: _containers.MessageMap[str, ScriptField]
    seq_no_primary_term: bool
    fields: _containers.RepeatedCompositeFieldContainer[FieldAndFormat]
    sort: _containers.RepeatedCompositeFieldContainer[SortCombinations]
    x_source: SourceConfig
    stored_fields: _containers.RepeatedScalarFieldContainer[str]
    track_scores: bool
    version: bool
    def __init__(self, name: _Optional[str] = ..., size: _Optional[int] = ..., collapse: _Optional[_Union[FieldCollapse, _Mapping]] = ..., docvalue_fields: _Optional[_Iterable[_Union[FieldAndFormat, _Mapping]]] = ..., explain: bool = ..., highlight: _Optional[_Union[Highlight, _Mapping]] = ..., ignore_unmapped: bool = ..., script_fields: _Optional[_Mapping[str, ScriptField]] = ..., seq_no_primary_term: bool = ..., fields: _Optional[_Iterable[_Union[FieldAndFormat, _Mapping]]] = ..., sort: _Optional[_Iterable[_Union[SortCombinations, _Mapping]]] = ..., x_source: _Optional[_Union[SourceConfig, _Mapping]] = ..., stored_fields: _Optional[_Iterable[str]] = ..., track_scores: bool = ..., version: bool = ..., **kwargs) -> None: ...

class ScriptField(_message.Message):
    __slots__ = ("script", "ignore_failure")
    SCRIPT_FIELD_NUMBER: _ClassVar[int]
    IGNORE_FAILURE_FIELD_NUMBER: _ClassVar[int]
    script: Script
    ignore_failure: bool
    def __init__(self, script: _Optional[_Union[Script, _Mapping]] = ..., ignore_failure: bool = ...) -> None: ...

class HighlighterType(_message.Message):
    __slots__ = ("builtin", "custom")
    BUILTIN_FIELD_NUMBER: _ClassVar[int]
    CUSTOM_FIELD_NUMBER: _ClassVar[int]
    builtin: BuiltinHighlighterType
    custom: str
    def __init__(self, builtin: _Optional[_Union[BuiltinHighlighterType, str]] = ..., custom: _Optional[str] = ...) -> None: ...

class SortCombinations(_message.Message):
    __slots__ = ("field", "field_with_direction", "field_with_order", "options")
    FIELD_FIELD_NUMBER: _ClassVar[int]
    FIELD_WITH_DIRECTION_FIELD_NUMBER: _ClassVar[int]
    FIELD_WITH_ORDER_FIELD_NUMBER: _ClassVar[int]
    OPTIONS_FIELD_NUMBER: _ClassVar[int]
    field: str
    field_with_direction: SortOrderMap
    field_with_order: FieldSortMap
    options: SortOptions
    def __init__(self, field: _Optional[str] = ..., field_with_direction: _Optional[_Union[SortOrderMap, _Mapping]] = ..., field_with_order: _Optional[_Union[FieldSortMap, _Mapping]] = ..., options: _Optional[_Union[SortOptions, _Mapping]] = ...) -> None: ...

class SortOrderMap(_message.Message):
    __slots__ = ("sort_order_map",)
    class SortOrderMapEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: SortOrder
        def __init__(self, key: _Optional[str] = ..., value: _Optional[_Union[SortOrder, str]] = ...) -> None: ...
    SORT_ORDER_MAP_FIELD_NUMBER: _ClassVar[int]
    sort_order_map: _containers.ScalarMap[str, SortOrder]
    def __init__(self, sort_order_map: _Optional[_Mapping[str, SortOrder]] = ...) -> None: ...

class FieldSortMap(_message.Message):
    __slots__ = ("field_sort_map",)
    class FieldSortMapEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: FieldSort
        def __init__(self, key: _Optional[str] = ..., value: _Optional[_Union[FieldSort, _Mapping]] = ...) -> None: ...
    FIELD_SORT_MAP_FIELD_NUMBER: _ClassVar[int]
    field_sort_map: _containers.MessageMap[str, FieldSort]
    def __init__(self, field_sort_map: _Optional[_Mapping[str, FieldSort]] = ...) -> None: ...

class SortOptions(_message.Message):
    __slots__ = ("x_score", "x_geo_distance", "x_script")
    X_SCORE_FIELD_NUMBER: _ClassVar[int]
    X_GEO_DISTANCE_FIELD_NUMBER: _ClassVar[int]
    X_SCRIPT_FIELD_NUMBER: _ClassVar[int]
    x_score: ScoreSort
    x_geo_distance: GeoDistanceSort
    x_script: ScriptSort
    def __init__(self, x_score: _Optional[_Union[ScoreSort, _Mapping]] = ..., x_geo_distance: _Optional[_Union[GeoDistanceSort, _Mapping]] = ..., x_script: _Optional[_Union[ScriptSort, _Mapping]] = ...) -> None: ...

class Highlight(_message.Message):
    __slots__ = ("type", "boundary_chars", "boundary_max_scan", "boundary_scanner", "boundary_scanner_locale", "force_source", "fragmenter", "fragment_offset", "fragment_size", "highlight_filter", "highlight_query", "max_fragment_length", "max_analyzer_offset", "no_match_size", "number_of_fragments", "options", "order", "phrase_limit", "post_tags", "pre_tags", "require_field_match", "tags_schema", "encoder", "fields")
    class FieldsEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: HighlightField
        def __init__(self, key: _Optional[str] = ..., value: _Optional[_Union[HighlightField, _Mapping]] = ...) -> None: ...
    TYPE_FIELD_NUMBER: _ClassVar[int]
    BOUNDARY_CHARS_FIELD_NUMBER: _ClassVar[int]
    BOUNDARY_MAX_SCAN_FIELD_NUMBER: _ClassVar[int]
    BOUNDARY_SCANNER_FIELD_NUMBER: _ClassVar[int]
    BOUNDARY_SCANNER_LOCALE_FIELD_NUMBER: _ClassVar[int]
    FORCE_SOURCE_FIELD_NUMBER: _ClassVar[int]
    FRAGMENTER_FIELD_NUMBER: _ClassVar[int]
    FRAGMENT_OFFSET_FIELD_NUMBER: _ClassVar[int]
    FRAGMENT_SIZE_FIELD_NUMBER: _ClassVar[int]
    HIGHLIGHT_FILTER_FIELD_NUMBER: _ClassVar[int]
    HIGHLIGHT_QUERY_FIELD_NUMBER: _ClassVar[int]
    MAX_FRAGMENT_LENGTH_FIELD_NUMBER: _ClassVar[int]
    MAX_ANALYZER_OFFSET_FIELD_NUMBER: _ClassVar[int]
    NO_MATCH_SIZE_FIELD_NUMBER: _ClassVar[int]
    NUMBER_OF_FRAGMENTS_FIELD_NUMBER: _ClassVar[int]
    OPTIONS_FIELD_NUMBER: _ClassVar[int]
    ORDER_FIELD_NUMBER: _ClassVar[int]
    PHRASE_LIMIT_FIELD_NUMBER: _ClassVar[int]
    POST_TAGS_FIELD_NUMBER: _ClassVar[int]
    PRE_TAGS_FIELD_NUMBER: _ClassVar[int]
    REQUIRE_FIELD_MATCH_FIELD_NUMBER: _ClassVar[int]
    TAGS_SCHEMA_FIELD_NUMBER: _ClassVar[int]
    ENCODER_FIELD_NUMBER: _ClassVar[int]
    FIELDS_FIELD_NUMBER: _ClassVar[int]
    type: HighlighterType
    boundary_chars: str
    boundary_max_scan: int
    boundary_scanner: BoundaryScanner
    boundary_scanner_locale: str
    force_source: bool
    fragmenter: HighlighterFragmenter
    fragment_offset: int
    fragment_size: int
    highlight_filter: bool
    highlight_query: QueryContainer
    max_fragment_length: int
    max_analyzer_offset: int
    no_match_size: int
    number_of_fragments: int
    options: ObjectMap
    order: HighlighterOrder
    phrase_limit: int
    post_tags: _containers.RepeatedScalarFieldContainer[str]
    pre_tags: _containers.RepeatedScalarFieldContainer[str]
    require_field_match: bool
    tags_schema: HighlighterTagsSchema
    encoder: HighlighterEncoder
    fields: _containers.MessageMap[str, HighlightField]
    def __init__(self, type: _Optional[_Union[HighlighterType, _Mapping]] = ..., boundary_chars: _Optional[str] = ..., boundary_max_scan: _Optional[int] = ..., boundary_scanner: _Optional[_Union[BoundaryScanner, str]] = ..., boundary_scanner_locale: _Optional[str] = ..., force_source: bool = ..., fragmenter: _Optional[_Union[HighlighterFragmenter, str]] = ..., fragment_offset: _Optional[int] = ..., fragment_size: _Optional[int] = ..., highlight_filter: bool = ..., highlight_query: _Optional[_Union[QueryContainer, _Mapping]] = ..., max_fragment_length: _Optional[int] = ..., max_analyzer_offset: _Optional[int] = ..., no_match_size: _Optional[int] = ..., number_of_fragments: _Optional[int] = ..., options: _Optional[_Union[ObjectMap, _Mapping]] = ..., order: _Optional[_Union[HighlighterOrder, str]] = ..., phrase_limit: _Optional[int] = ..., post_tags: _Optional[_Iterable[str]] = ..., pre_tags: _Optional[_Iterable[str]] = ..., require_field_match: bool = ..., tags_schema: _Optional[_Union[HighlighterTagsSchema, str]] = ..., encoder: _Optional[_Union[HighlighterEncoder, str]] = ..., fields: _Optional[_Mapping[str, HighlightField]] = ...) -> None: ...

class HighlightField(_message.Message):
    __slots__ = ("type", "boundary_chars", "boundary_max_scan", "boundary_scanner", "boundary_scanner_locale", "force_source", "fragmenter", "fragment_size", "highlight_filter", "highlight_query", "max_fragment_length", "max_analyzer_offset", "no_match_size", "number_of_fragments", "options", "order", "phrase_limit", "post_tags", "pre_tags", "require_field_match", "tags_schema", "fragment_offset", "matched_fields")
    TYPE_FIELD_NUMBER: _ClassVar[int]
    BOUNDARY_CHARS_FIELD_NUMBER: _ClassVar[int]
    BOUNDARY_MAX_SCAN_FIELD_NUMBER: _ClassVar[int]
    BOUNDARY_SCANNER_FIELD_NUMBER: _ClassVar[int]
    BOUNDARY_SCANNER_LOCALE_FIELD_NUMBER: _ClassVar[int]
    FORCE_SOURCE_FIELD_NUMBER: _ClassVar[int]
    FRAGMENTER_FIELD_NUMBER: _ClassVar[int]
    FRAGMENT_SIZE_FIELD_NUMBER: _ClassVar[int]
    HIGHLIGHT_FILTER_FIELD_NUMBER: _ClassVar[int]
    HIGHLIGHT_QUERY_FIELD_NUMBER: _ClassVar[int]
    MAX_FRAGMENT_LENGTH_FIELD_NUMBER: _ClassVar[int]
    MAX_ANALYZER_OFFSET_FIELD_NUMBER: _ClassVar[int]
    NO_MATCH_SIZE_FIELD_NUMBER: _ClassVar[int]
    NUMBER_OF_FRAGMENTS_FIELD_NUMBER: _ClassVar[int]
    OPTIONS_FIELD_NUMBER: _ClassVar[int]
    ORDER_FIELD_NUMBER: _ClassVar[int]
    PHRASE_LIMIT_FIELD_NUMBER: _ClassVar[int]
    POST_TAGS_FIELD_NUMBER: _ClassVar[int]
    PRE_TAGS_FIELD_NUMBER: _ClassVar[int]
    REQUIRE_FIELD_MATCH_FIELD_NUMBER: _ClassVar[int]
    TAGS_SCHEMA_FIELD_NUMBER: _ClassVar[int]
    FRAGMENT_OFFSET_FIELD_NUMBER: _ClassVar[int]
    MATCHED_FIELDS_FIELD_NUMBER: _ClassVar[int]
    type: HighlighterType
    boundary_chars: str
    boundary_max_scan: int
    boundary_scanner: BoundaryScanner
    boundary_scanner_locale: str
    force_source: bool
    fragmenter: HighlighterFragmenter
    fragment_size: int
    highlight_filter: bool
    highlight_query: QueryContainer
    max_fragment_length: int
    max_analyzer_offset: int
    no_match_size: int
    number_of_fragments: int
    options: ObjectMap
    order: HighlighterOrder
    phrase_limit: int
    post_tags: _containers.RepeatedScalarFieldContainer[str]
    pre_tags: _containers.RepeatedScalarFieldContainer[str]
    require_field_match: bool
    tags_schema: HighlighterTagsSchema
    fragment_offset: int
    matched_fields: _containers.RepeatedScalarFieldContainer[str]
    def __init__(self, type: _Optional[_Union[HighlighterType, _Mapping]] = ..., boundary_chars: _Optional[str] = ..., boundary_max_scan: _Optional[int] = ..., boundary_scanner: _Optional[_Union[BoundaryScanner, str]] = ..., boundary_scanner_locale: _Optional[str] = ..., force_source: bool = ..., fragmenter: _Optional[_Union[HighlighterFragmenter, str]] = ..., fragment_size: _Optional[int] = ..., highlight_filter: bool = ..., highlight_query: _Optional[_Union[QueryContainer, _Mapping]] = ..., max_fragment_length: _Optional[int] = ..., max_analyzer_offset: _Optional[int] = ..., no_match_size: _Optional[int] = ..., number_of_fragments: _Optional[int] = ..., options: _Optional[_Union[ObjectMap, _Mapping]] = ..., order: _Optional[_Union[HighlighterOrder, str]] = ..., phrase_limit: _Optional[int] = ..., post_tags: _Optional[_Iterable[str]] = ..., pre_tags: _Optional[_Iterable[str]] = ..., require_field_match: bool = ..., tags_schema: _Optional[_Union[HighlighterTagsSchema, str]] = ..., fragment_offset: _Optional[int] = ..., matched_fields: _Optional[_Iterable[str]] = ...) -> None: ...

class FieldSort(_message.Message):
    __slots__ = ("missing", "mode", "nested", "order", "unmapped_type", "numeric_type")
    MISSING_FIELD_NUMBER: _ClassVar[int]
    MODE_FIELD_NUMBER: _ClassVar[int]
    NESTED_FIELD_NUMBER: _ClassVar[int]
    ORDER_FIELD_NUMBER: _ClassVar[int]
    UNMAPPED_TYPE_FIELD_NUMBER: _ClassVar[int]
    NUMERIC_TYPE_FIELD_NUMBER: _ClassVar[int]
    missing: FieldValue
    mode: SortMode
    nested: NestedSortValue
    order: SortOrder
    unmapped_type: FieldType
    numeric_type: FieldSortNumericType
    def __init__(self, missing: _Optional[_Union[FieldValue, _Mapping]] = ..., mode: _Optional[_Union[SortMode, str]] = ..., nested: _Optional[_Union[NestedSortValue, _Mapping]] = ..., order: _Optional[_Union[SortOrder, str]] = ..., unmapped_type: _Optional[_Union[FieldType, str]] = ..., numeric_type: _Optional[_Union[FieldSortNumericType, str]] = ...) -> None: ...

class GeoDistanceSort(_message.Message):
    __slots__ = ("mode", "distance_type", "ignore_unmapped", "nested", "order", "unit", "validation_method", "location")
    class LocationEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: GeoLocationArray
        def __init__(self, key: _Optional[str] = ..., value: _Optional[_Union[GeoLocationArray, _Mapping]] = ...) -> None: ...
    MODE_FIELD_NUMBER: _ClassVar[int]
    DISTANCE_TYPE_FIELD_NUMBER: _ClassVar[int]
    IGNORE_UNMAPPED_FIELD_NUMBER: _ClassVar[int]
    NESTED_FIELD_NUMBER: _ClassVar[int]
    ORDER_FIELD_NUMBER: _ClassVar[int]
    UNIT_FIELD_NUMBER: _ClassVar[int]
    VALIDATION_METHOD_FIELD_NUMBER: _ClassVar[int]
    LOCATION_FIELD_NUMBER: _ClassVar[int]
    mode: SortMode
    distance_type: GeoDistanceType
    ignore_unmapped: bool
    nested: NestedSortValue
    order: SortOrder
    unit: DistanceUnit
    validation_method: GeoValidationMethod
    location: _containers.MessageMap[str, GeoLocationArray]
    def __init__(self, mode: _Optional[_Union[SortMode, str]] = ..., distance_type: _Optional[_Union[GeoDistanceType, str]] = ..., ignore_unmapped: bool = ..., nested: _Optional[_Union[NestedSortValue, _Mapping]] = ..., order: _Optional[_Union[SortOrder, str]] = ..., unit: _Optional[_Union[DistanceUnit, str]] = ..., validation_method: _Optional[_Union[GeoValidationMethod, str]] = ..., location: _Optional[_Mapping[str, GeoLocationArray]] = ...) -> None: ...

class ScoreSort(_message.Message):
    __slots__ = ("order",)
    ORDER_FIELD_NUMBER: _ClassVar[int]
    order: SortOrder
    def __init__(self, order: _Optional[_Union[SortOrder, str]] = ...) -> None: ...

class GeoLocationArray(_message.Message):
    __slots__ = ("geo_location_array",)
    GEO_LOCATION_ARRAY_FIELD_NUMBER: _ClassVar[int]
    geo_location_array: _containers.RepeatedCompositeFieldContainer[GeoLocation]
    def __init__(self, geo_location_array: _Optional[_Iterable[_Union[GeoLocation, _Mapping]]] = ...) -> None: ...

class ScriptSort(_message.Message):
    __slots__ = ("script", "order", "type", "mode", "nested")
    SCRIPT_FIELD_NUMBER: _ClassVar[int]
    ORDER_FIELD_NUMBER: _ClassVar[int]
    TYPE_FIELD_NUMBER: _ClassVar[int]
    MODE_FIELD_NUMBER: _ClassVar[int]
    NESTED_FIELD_NUMBER: _ClassVar[int]
    script: Script
    order: SortOrder
    type: ScriptSortType
    mode: SortMode
    nested: NestedSortValue
    def __init__(self, script: _Optional[_Union[Script, _Mapping]] = ..., order: _Optional[_Union[SortOrder, str]] = ..., type: _Optional[_Union[ScriptSortType, str]] = ..., mode: _Optional[_Union[SortMode, str]] = ..., nested: _Optional[_Union[NestedSortValue, _Mapping]] = ...) -> None: ...

class NestedSortValue(_message.Message):
    __slots__ = ("path", "filter", "max_children", "nested")
    PATH_FIELD_NUMBER: _ClassVar[int]
    FILTER_FIELD_NUMBER: _ClassVar[int]
    MAX_CHILDREN_FIELD_NUMBER: _ClassVar[int]
    NESTED_FIELD_NUMBER: _ClassVar[int]
    path: str
    filter: QueryContainer
    max_children: int
    nested: NestedSortValue
    def __init__(self, path: _Optional[str] = ..., filter: _Optional[_Union[QueryContainer, _Mapping]] = ..., max_children: _Optional[int] = ..., nested: _Optional[_Union[NestedSortValue, _Mapping]] = ...) -> None: ...

class FieldAndFormat(_message.Message):
    __slots__ = ("field", "format")
    FIELD_FIELD_NUMBER: _ClassVar[int]
    FORMAT_FIELD_NUMBER: _ClassVar[int]
    field: str
    format: str
    def __init__(self, field: _Optional[str] = ..., format: _Optional[str] = ...) -> None: ...

class FieldCollapse(_message.Message):
    __slots__ = ("field", "inner_hits", "max_concurrent_group_searches")
    FIELD_FIELD_NUMBER: _ClassVar[int]
    INNER_HITS_FIELD_NUMBER: _ClassVar[int]
    MAX_CONCURRENT_GROUP_SEARCHES_FIELD_NUMBER: _ClassVar[int]
    field: str
    inner_hits: _containers.RepeatedCompositeFieldContainer[InnerHits]
    max_concurrent_group_searches: int
    def __init__(self, field: _Optional[str] = ..., inner_hits: _Optional[_Iterable[_Union[InnerHits, _Mapping]]] = ..., max_concurrent_group_searches: _Optional[int] = ...) -> None: ...

class ExistsQuery(_message.Message):
    __slots__ = ("field", "boost", "x_name")
    FIELD_FIELD_NUMBER: _ClassVar[int]
    BOOST_FIELD_NUMBER: _ClassVar[int]
    X_NAME_FIELD_NUMBER: _ClassVar[int]
    field: str
    boost: float
    x_name: str
    def __init__(self, field: _Optional[str] = ..., boost: _Optional[float] = ..., x_name: _Optional[str] = ...) -> None: ...

class WildcardQuery(_message.Message):
    __slots__ = ("field", "boost", "x_name", "case_insensitive", "rewrite_deprecated", "value", "wildcard", "rewrite")
    FIELD_FIELD_NUMBER: _ClassVar[int]
    BOOST_FIELD_NUMBER: _ClassVar[int]
    X_NAME_FIELD_NUMBER: _ClassVar[int]
    CASE_INSENSITIVE_FIELD_NUMBER: _ClassVar[int]
    REWRITE_DEPRECATED_FIELD_NUMBER: _ClassVar[int]
    VALUE_FIELD_NUMBER: _ClassVar[int]
    WILDCARD_FIELD_NUMBER: _ClassVar[int]
    REWRITE_FIELD_NUMBER: _ClassVar[int]
    field: str
    boost: float
    x_name: str
    case_insensitive: bool
    rewrite_deprecated: MultiTermQueryRewrite
    value: str
    wildcard: str
    rewrite: str
    def __init__(self, field: _Optional[str] = ..., boost: _Optional[float] = ..., x_name: _Optional[str] = ..., case_insensitive: bool = ..., rewrite_deprecated: _Optional[_Union[MultiTermQueryRewrite, str]] = ..., value: _Optional[str] = ..., wildcard: _Optional[str] = ..., rewrite: _Optional[str] = ...) -> None: ...

class KnnQuery(_message.Message):
    __slots__ = ("field", "vector", "k", "min_score", "max_distance", "filter", "boost", "x_name", "method_parameters", "rescore", "expand_nested_docs")
    FIELD_FIELD_NUMBER: _ClassVar[int]
    VECTOR_FIELD_NUMBER: _ClassVar[int]
    K_FIELD_NUMBER: _ClassVar[int]
    MIN_SCORE_FIELD_NUMBER: _ClassVar[int]
    MAX_DISTANCE_FIELD_NUMBER: _ClassVar[int]
    FILTER_FIELD_NUMBER: _ClassVar[int]
    BOOST_FIELD_NUMBER: _ClassVar[int]
    X_NAME_FIELD_NUMBER: _ClassVar[int]
    METHOD_PARAMETERS_FIELD_NUMBER: _ClassVar[int]
    RESCORE_FIELD_NUMBER: _ClassVar[int]
    EXPAND_NESTED_DOCS_FIELD_NUMBER: _ClassVar[int]
    field: str
    vector: _containers.RepeatedScalarFieldContainer[float]
    k: int
    min_score: float
    max_distance: float
    filter: QueryContainer
    boost: float
    x_name: str
    method_parameters: ObjectMap
    rescore: KnnQueryRescore
    expand_nested_docs: bool
    def __init__(self, field: _Optional[str] = ..., vector: _Optional[_Iterable[float]] = ..., k: _Optional[int] = ..., min_score: _Optional[float] = ..., max_distance: _Optional[float] = ..., filter: _Optional[_Union[QueryContainer, _Mapping]] = ..., boost: _Optional[float] = ..., x_name: _Optional[str] = ..., method_parameters: _Optional[_Union[ObjectMap, _Mapping]] = ..., rescore: _Optional[_Union[KnnQueryRescore, _Mapping]] = ..., expand_nested_docs: bool = ...) -> None: ...

class RescoreContext(_message.Message):
    __slots__ = ("oversample_factor",)
    OVERSAMPLE_FACTOR_FIELD_NUMBER: _ClassVar[int]
    oversample_factor: float
    def __init__(self, oversample_factor: _Optional[float] = ...) -> None: ...

class KnnQueryRescore(_message.Message):
    __slots__ = ("enable", "context")
    ENABLE_FIELD_NUMBER: _ClassVar[int]
    CONTEXT_FIELD_NUMBER: _ClassVar[int]
    enable: bool
    context: RescoreContext
    def __init__(self, enable: bool = ..., context: _Optional[_Union[RescoreContext, _Mapping]] = ...) -> None: ...

class MatchQuery(_message.Message):
    __slots__ = ("field", "query", "boost", "x_name", "analyzer", "auto_generate_synonyms_phrase_query", "fuzziness", "fuzzy_rewrite_deprecated", "fuzzy_transpositions", "lenient", "max_expansions", "minimum_should_match", "operator", "prefix_length", "zero_terms_query", "fuzzy_rewrite")
    FIELD_FIELD_NUMBER: _ClassVar[int]
    QUERY_FIELD_NUMBER: _ClassVar[int]
    BOOST_FIELD_NUMBER: _ClassVar[int]
    X_NAME_FIELD_NUMBER: _ClassVar[int]
    ANALYZER_FIELD_NUMBER: _ClassVar[int]
    AUTO_GENERATE_SYNONYMS_PHRASE_QUERY_FIELD_NUMBER: _ClassVar[int]
    FUZZINESS_FIELD_NUMBER: _ClassVar[int]
    FUZZY_REWRITE_DEPRECATED_FIELD_NUMBER: _ClassVar[int]
    FUZZY_TRANSPOSITIONS_FIELD_NUMBER: _ClassVar[int]
    LENIENT_FIELD_NUMBER: _ClassVar[int]
    MAX_EXPANSIONS_FIELD_NUMBER: _ClassVar[int]
    MINIMUM_SHOULD_MATCH_FIELD_NUMBER: _ClassVar[int]
    OPERATOR_FIELD_NUMBER: _ClassVar[int]
    PREFIX_LENGTH_FIELD_NUMBER: _ClassVar[int]
    ZERO_TERMS_QUERY_FIELD_NUMBER: _ClassVar[int]
    FUZZY_REWRITE_FIELD_NUMBER: _ClassVar[int]
    field: str
    query: FieldValue
    boost: float
    x_name: str
    analyzer: str
    auto_generate_synonyms_phrase_query: bool
    fuzziness: Fuzziness
    fuzzy_rewrite_deprecated: MultiTermQueryRewrite
    fuzzy_transpositions: bool
    lenient: bool
    max_expansions: int
    minimum_should_match: MinimumShouldMatch
    operator: Operator
    prefix_length: int
    zero_terms_query: ZeroTermsQuery
    fuzzy_rewrite: str
    def __init__(self, field: _Optional[str] = ..., query: _Optional[_Union[FieldValue, _Mapping]] = ..., boost: _Optional[float] = ..., x_name: _Optional[str] = ..., analyzer: _Optional[str] = ..., auto_generate_synonyms_phrase_query: bool = ..., fuzziness: _Optional[_Union[Fuzziness, _Mapping]] = ..., fuzzy_rewrite_deprecated: _Optional[_Union[MultiTermQueryRewrite, str]] = ..., fuzzy_transpositions: bool = ..., lenient: bool = ..., max_expansions: _Optional[int] = ..., minimum_should_match: _Optional[_Union[MinimumShouldMatch, _Mapping]] = ..., operator: _Optional[_Union[Operator, str]] = ..., prefix_length: _Optional[int] = ..., zero_terms_query: _Optional[_Union[ZeroTermsQuery, str]] = ..., fuzzy_rewrite: _Optional[str] = ...) -> None: ...

class BoolQuery(_message.Message):
    __slots__ = ("boost", "x_name", "filter", "minimum_should_match", "must", "must_not", "should", "adjust_pure_negative")
    BOOST_FIELD_NUMBER: _ClassVar[int]
    X_NAME_FIELD_NUMBER: _ClassVar[int]
    FILTER_FIELD_NUMBER: _ClassVar[int]
    MINIMUM_SHOULD_MATCH_FIELD_NUMBER: _ClassVar[int]
    MUST_FIELD_NUMBER: _ClassVar[int]
    MUST_NOT_FIELD_NUMBER: _ClassVar[int]
    SHOULD_FIELD_NUMBER: _ClassVar[int]
    ADJUST_PURE_NEGATIVE_FIELD_NUMBER: _ClassVar[int]
    boost: float
    x_name: str
    filter: _containers.RepeatedCompositeFieldContainer[QueryContainer]
    minimum_should_match: MinimumShouldMatch
    must: _containers.RepeatedCompositeFieldContainer[QueryContainer]
    must_not: _containers.RepeatedCompositeFieldContainer[QueryContainer]
    should: _containers.RepeatedCompositeFieldContainer[QueryContainer]
    adjust_pure_negative: bool
    def __init__(self, boost: _Optional[float] = ..., x_name: _Optional[str] = ..., filter: _Optional[_Iterable[_Union[QueryContainer, _Mapping]]] = ..., minimum_should_match: _Optional[_Union[MinimumShouldMatch, _Mapping]] = ..., must: _Optional[_Iterable[_Union[QueryContainer, _Mapping]]] = ..., must_not: _Optional[_Iterable[_Union[QueryContainer, _Mapping]]] = ..., should: _Optional[_Iterable[_Union[QueryContainer, _Mapping]]] = ..., adjust_pure_negative: bool = ...) -> None: ...

class MinimumShouldMatch(_message.Message):
    __slots__ = ("int32", "string")
    INT32_FIELD_NUMBER: _ClassVar[int]
    STRING_FIELD_NUMBER: _ClassVar[int]
    int32: int
    string: str
    def __init__(self, int32: _Optional[int] = ..., string: _Optional[str] = ...) -> None: ...

class ConstantScoreQuery(_message.Message):
    __slots__ = ("filter", "boost", "x_name")
    FILTER_FIELD_NUMBER: _ClassVar[int]
    BOOST_FIELD_NUMBER: _ClassVar[int]
    X_NAME_FIELD_NUMBER: _ClassVar[int]
    filter: QueryContainer
    boost: float
    x_name: str
    def __init__(self, filter: _Optional[_Union[QueryContainer, _Mapping]] = ..., boost: _Optional[float] = ..., x_name: _Optional[str] = ...) -> None: ...

class FunctionScoreQuery(_message.Message):
    __slots__ = ("boost", "x_name", "boost_mode", "functions", "max_boost", "min_score", "query", "score_mode")
    BOOST_FIELD_NUMBER: _ClassVar[int]
    X_NAME_FIELD_NUMBER: _ClassVar[int]
    BOOST_MODE_FIELD_NUMBER: _ClassVar[int]
    FUNCTIONS_FIELD_NUMBER: _ClassVar[int]
    MAX_BOOST_FIELD_NUMBER: _ClassVar[int]
    MIN_SCORE_FIELD_NUMBER: _ClassVar[int]
    QUERY_FIELD_NUMBER: _ClassVar[int]
    SCORE_MODE_FIELD_NUMBER: _ClassVar[int]
    boost: float
    x_name: str
    boost_mode: FunctionBoostMode
    functions: _containers.RepeatedCompositeFieldContainer[FunctionScoreContainer]
    max_boost: float
    min_score: float
    query: QueryContainer
    score_mode: FunctionScoreMode
    def __init__(self, boost: _Optional[float] = ..., x_name: _Optional[str] = ..., boost_mode: _Optional[_Union[FunctionBoostMode, str]] = ..., functions: _Optional[_Iterable[_Union[FunctionScoreContainer, _Mapping]]] = ..., max_boost: _Optional[float] = ..., min_score: _Optional[float] = ..., query: _Optional[_Union[QueryContainer, _Mapping]] = ..., score_mode: _Optional[_Union[FunctionScoreMode, str]] = ...) -> None: ...

class FunctionScoreContainer(_message.Message):
    __slots__ = ("filter", "weight", "exp", "gauss", "linear", "field_value_factor", "random_score", "script_score")
    FILTER_FIELD_NUMBER: _ClassVar[int]
    WEIGHT_FIELD_NUMBER: _ClassVar[int]
    EXP_FIELD_NUMBER: _ClassVar[int]
    GAUSS_FIELD_NUMBER: _ClassVar[int]
    LINEAR_FIELD_NUMBER: _ClassVar[int]
    FIELD_VALUE_FACTOR_FIELD_NUMBER: _ClassVar[int]
    RANDOM_SCORE_FIELD_NUMBER: _ClassVar[int]
    SCRIPT_SCORE_FIELD_NUMBER: _ClassVar[int]
    filter: QueryContainer
    weight: float
    exp: DecayFunction
    gauss: DecayFunction
    linear: DecayFunction
    field_value_factor: FieldValueFactorScoreFunction
    random_score: RandomScoreFunction
    script_score: ScriptScoreFunction
    def __init__(self, filter: _Optional[_Union[QueryContainer, _Mapping]] = ..., weight: _Optional[float] = ..., exp: _Optional[_Union[DecayFunction, _Mapping]] = ..., gauss: _Optional[_Union[DecayFunction, _Mapping]] = ..., linear: _Optional[_Union[DecayFunction, _Mapping]] = ..., field_value_factor: _Optional[_Union[FieldValueFactorScoreFunction, _Mapping]] = ..., random_score: _Optional[_Union[RandomScoreFunction, _Mapping]] = ..., script_score: _Optional[_Union[ScriptScoreFunction, _Mapping]] = ...) -> None: ...

class DecayFunction(_message.Message):
    __slots__ = ("multi_value_mode", "placement")
    class PlacementEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: DecayPlacement
        def __init__(self, key: _Optional[str] = ..., value: _Optional[_Union[DecayPlacement, _Mapping]] = ...) -> None: ...
    MULTI_VALUE_MODE_FIELD_NUMBER: _ClassVar[int]
    PLACEMENT_FIELD_NUMBER: _ClassVar[int]
    multi_value_mode: MultiValueMode
    placement: _containers.MessageMap[str, DecayPlacement]
    def __init__(self, multi_value_mode: _Optional[_Union[MultiValueMode, str]] = ..., placement: _Optional[_Mapping[str, DecayPlacement]] = ...) -> None: ...

class DecayPlacement(_message.Message):
    __slots__ = ("date_decay_placement", "geo_decay_placement", "numeric_decay_placement")
    DATE_DECAY_PLACEMENT_FIELD_NUMBER: _ClassVar[int]
    GEO_DECAY_PLACEMENT_FIELD_NUMBER: _ClassVar[int]
    NUMERIC_DECAY_PLACEMENT_FIELD_NUMBER: _ClassVar[int]
    date_decay_placement: DateDecayPlacement
    geo_decay_placement: GeoDecayPlacement
    numeric_decay_placement: NumericDecayPlacement
    def __init__(self, date_decay_placement: _Optional[_Union[DateDecayPlacement, _Mapping]] = ..., geo_decay_placement: _Optional[_Union[GeoDecayPlacement, _Mapping]] = ..., numeric_decay_placement: _Optional[_Union[NumericDecayPlacement, _Mapping]] = ...) -> None: ...

class DateDecayPlacement(_message.Message):
    __slots__ = ("scale", "decay", "offset", "origin")
    SCALE_FIELD_NUMBER: _ClassVar[int]
    DECAY_FIELD_NUMBER: _ClassVar[int]
    OFFSET_FIELD_NUMBER: _ClassVar[int]
    ORIGIN_FIELD_NUMBER: _ClassVar[int]
    scale: str
    decay: float
    offset: str
    origin: str
    def __init__(self, scale: _Optional[str] = ..., decay: _Optional[float] = ..., offset: _Optional[str] = ..., origin: _Optional[str] = ...) -> None: ...

class GeoDecayPlacement(_message.Message):
    __slots__ = ("scale", "origin", "decay", "offset")
    SCALE_FIELD_NUMBER: _ClassVar[int]
    ORIGIN_FIELD_NUMBER: _ClassVar[int]
    DECAY_FIELD_NUMBER: _ClassVar[int]
    OFFSET_FIELD_NUMBER: _ClassVar[int]
    scale: str
    origin: GeoLocation
    decay: float
    offset: str
    def __init__(self, scale: _Optional[str] = ..., origin: _Optional[_Union[GeoLocation, _Mapping]] = ..., decay: _Optional[float] = ..., offset: _Optional[str] = ...) -> None: ...

class NumericDecayPlacement(_message.Message):
    __slots__ = ("scale", "origin", "decay", "offset")
    SCALE_FIELD_NUMBER: _ClassVar[int]
    ORIGIN_FIELD_NUMBER: _ClassVar[int]
    DECAY_FIELD_NUMBER: _ClassVar[int]
    OFFSET_FIELD_NUMBER: _ClassVar[int]
    scale: float
    origin: float
    decay: float
    offset: float
    def __init__(self, scale: _Optional[float] = ..., origin: _Optional[float] = ..., decay: _Optional[float] = ..., offset: _Optional[float] = ...) -> None: ...

class ScriptScoreFunction(_message.Message):
    __slots__ = ("script",)
    SCRIPT_FIELD_NUMBER: _ClassVar[int]
    script: Script
    def __init__(self, script: _Optional[_Union[Script, _Mapping]] = ...) -> None: ...

class PrefixQuery(_message.Message):
    __slots__ = ("field", "value", "boost", "x_name", "rewrite_deprecated", "case_insensitive", "rewrite")
    FIELD_FIELD_NUMBER: _ClassVar[int]
    VALUE_FIELD_NUMBER: _ClassVar[int]
    BOOST_FIELD_NUMBER: _ClassVar[int]
    X_NAME_FIELD_NUMBER: _ClassVar[int]
    REWRITE_DEPRECATED_FIELD_NUMBER: _ClassVar[int]
    CASE_INSENSITIVE_FIELD_NUMBER: _ClassVar[int]
    REWRITE_FIELD_NUMBER: _ClassVar[int]
    field: str
    value: str
    boost: float
    x_name: str
    rewrite_deprecated: MultiTermQueryRewrite
    case_insensitive: bool
    rewrite: str
    def __init__(self, field: _Optional[str] = ..., value: _Optional[str] = ..., boost: _Optional[float] = ..., x_name: _Optional[str] = ..., rewrite_deprecated: _Optional[_Union[MultiTermQueryRewrite, str]] = ..., case_insensitive: bool = ..., rewrite: _Optional[str] = ...) -> None: ...

class TermsQueryField(_message.Message):
    __slots__ = ("value", "lookup")
    VALUE_FIELD_NUMBER: _ClassVar[int]
    LOOKUP_FIELD_NUMBER: _ClassVar[int]
    value: FieldValueArray
    lookup: TermsLookup
    def __init__(self, value: _Optional[_Union[FieldValueArray, _Mapping]] = ..., lookup: _Optional[_Union[TermsLookup, _Mapping]] = ...) -> None: ...

class TermsLookup(_message.Message):
    __slots__ = ("index", "id", "path", "routing", "store", "id_2", "query")
    INDEX_FIELD_NUMBER: _ClassVar[int]
    ID_FIELD_NUMBER: _ClassVar[int]
    PATH_FIELD_NUMBER: _ClassVar[int]
    ROUTING_FIELD_NUMBER: _ClassVar[int]
    STORE_FIELD_NUMBER: _ClassVar[int]
    ID_2_FIELD_NUMBER: _ClassVar[int]
    QUERY_FIELD_NUMBER: _ClassVar[int]
    index: str
    id: str
    path: str
    routing: str
    store: bool
    id_2: str
    query: QueryContainer
    def __init__(self, index: _Optional[str] = ..., id: _Optional[str] = ..., path: _Optional[str] = ..., routing: _Optional[str] = ..., store: bool = ..., id_2: _Optional[str] = ..., query: _Optional[_Union[QueryContainer, _Mapping]] = ...) -> None: ...

class FieldValueArray(_message.Message):
    __slots__ = ("field_value_array",)
    FIELD_VALUE_ARRAY_FIELD_NUMBER: _ClassVar[int]
    field_value_array: _containers.RepeatedCompositeFieldContainer[FieldValue]
    def __init__(self, field_value_array: _Optional[_Iterable[_Union[FieldValue, _Mapping]]] = ...) -> None: ...

class TermsSetQuery(_message.Message):
    __slots__ = ("field", "terms", "boost", "x_name", "minimum_should_match_field", "minimum_should_match_script")
    FIELD_FIELD_NUMBER: _ClassVar[int]
    TERMS_FIELD_NUMBER: _ClassVar[int]
    BOOST_FIELD_NUMBER: _ClassVar[int]
    X_NAME_FIELD_NUMBER: _ClassVar[int]
    MINIMUM_SHOULD_MATCH_FIELD_FIELD_NUMBER: _ClassVar[int]
    MINIMUM_SHOULD_MATCH_SCRIPT_FIELD_NUMBER: _ClassVar[int]
    field: str
    terms: _containers.RepeatedScalarFieldContainer[str]
    boost: float
    x_name: str
    minimum_should_match_field: str
    minimum_should_match_script: Script
    def __init__(self, field: _Optional[str] = ..., terms: _Optional[_Iterable[str]] = ..., boost: _Optional[float] = ..., x_name: _Optional[str] = ..., minimum_should_match_field: _Optional[str] = ..., minimum_should_match_script: _Optional[_Union[Script, _Mapping]] = ...) -> None: ...

class RegexpQuery(_message.Message):
    __slots__ = ("field", "value", "boost", "x_name", "case_insensitive", "flags", "max_determinized_states", "rewrite_deprecated", "rewrite")
    FIELD_FIELD_NUMBER: _ClassVar[int]
    VALUE_FIELD_NUMBER: _ClassVar[int]
    BOOST_FIELD_NUMBER: _ClassVar[int]
    X_NAME_FIELD_NUMBER: _ClassVar[int]
    CASE_INSENSITIVE_FIELD_NUMBER: _ClassVar[int]
    FLAGS_FIELD_NUMBER: _ClassVar[int]
    MAX_DETERMINIZED_STATES_FIELD_NUMBER: _ClassVar[int]
    REWRITE_DEPRECATED_FIELD_NUMBER: _ClassVar[int]
    REWRITE_FIELD_NUMBER: _ClassVar[int]
    field: str
    value: str
    boost: float
    x_name: str
    case_insensitive: bool
    flags: str
    max_determinized_states: int
    rewrite_deprecated: MultiTermQueryRewrite
    rewrite: str
    def __init__(self, field: _Optional[str] = ..., value: _Optional[str] = ..., boost: _Optional[float] = ..., x_name: _Optional[str] = ..., case_insensitive: bool = ..., flags: _Optional[str] = ..., max_determinized_states: _Optional[int] = ..., rewrite_deprecated: _Optional[_Union[MultiTermQueryRewrite, str]] = ..., rewrite: _Optional[str] = ...) -> None: ...

class TermQuery(_message.Message):
    __slots__ = ("field", "boost", "x_name", "value", "case_insensitive")
    FIELD_FIELD_NUMBER: _ClassVar[int]
    BOOST_FIELD_NUMBER: _ClassVar[int]
    X_NAME_FIELD_NUMBER: _ClassVar[int]
    VALUE_FIELD_NUMBER: _ClassVar[int]
    CASE_INSENSITIVE_FIELD_NUMBER: _ClassVar[int]
    field: str
    boost: float
    x_name: str
    value: FieldValue
    case_insensitive: bool
    def __init__(self, field: _Optional[str] = ..., boost: _Optional[float] = ..., x_name: _Optional[str] = ..., value: _Optional[_Union[FieldValue, _Mapping]] = ..., case_insensitive: bool = ...) -> None: ...

class RandomScoreFunction(_message.Message):
    __slots__ = ("field", "seed")
    FIELD_FIELD_NUMBER: _ClassVar[int]
    SEED_FIELD_NUMBER: _ClassVar[int]
    field: str
    seed: RandomScoreFunctionSeed
    def __init__(self, field: _Optional[str] = ..., seed: _Optional[_Union[RandomScoreFunctionSeed, _Mapping]] = ...) -> None: ...

class RandomScoreFunctionSeed(_message.Message):
    __slots__ = ("int32", "int64", "string")
    INT32_FIELD_NUMBER: _ClassVar[int]
    INT64_FIELD_NUMBER: _ClassVar[int]
    STRING_FIELD_NUMBER: _ClassVar[int]
    int32: int
    int64: int
    string: str
    def __init__(self, int32: _Optional[int] = ..., int64: _Optional[int] = ..., string: _Optional[str] = ...) -> None: ...

class RangeQuery(_message.Message):
    __slots__ = ("number_range_query", "date_range_query")
    NUMBER_RANGE_QUERY_FIELD_NUMBER: _ClassVar[int]
    DATE_RANGE_QUERY_FIELD_NUMBER: _ClassVar[int]
    number_range_query: NumberRangeQuery
    date_range_query: DateRangeQuery
    def __init__(self, number_range_query: _Optional[_Union[NumberRangeQuery, _Mapping]] = ..., date_range_query: _Optional[_Union[DateRangeQuery, _Mapping]] = ...) -> None: ...

class NumberRangeQuery(_message.Message):
    __slots__ = ("field", "boost", "x_name", "relation", "gt", "gte", "lt", "lte", "to", "include_lower", "include_upper")
    FIELD_FIELD_NUMBER: _ClassVar[int]
    BOOST_FIELD_NUMBER: _ClassVar[int]
    X_NAME_FIELD_NUMBER: _ClassVar[int]
    RELATION_FIELD_NUMBER: _ClassVar[int]
    GT_FIELD_NUMBER: _ClassVar[int]
    GTE_FIELD_NUMBER: _ClassVar[int]
    LT_FIELD_NUMBER: _ClassVar[int]
    LTE_FIELD_NUMBER: _ClassVar[int]
    FROM_FIELD_NUMBER: _ClassVar[int]
    TO_FIELD_NUMBER: _ClassVar[int]
    INCLUDE_LOWER_FIELD_NUMBER: _ClassVar[int]
    INCLUDE_UPPER_FIELD_NUMBER: _ClassVar[int]
    field: str
    boost: float
    x_name: str
    relation: RangeRelation
    gt: float
    gte: float
    lt: float
    lte: float
    to: NumberRangeQueryAllOfTo
    include_lower: bool
    include_upper: bool
    def __init__(self, field: _Optional[str] = ..., boost: _Optional[float] = ..., x_name: _Optional[str] = ..., relation: _Optional[_Union[RangeRelation, str]] = ..., gt: _Optional[float] = ..., gte: _Optional[float] = ..., lt: _Optional[float] = ..., lte: _Optional[float] = ..., to: _Optional[_Union[NumberRangeQueryAllOfTo, _Mapping]] = ..., include_lower: bool = ..., include_upper: bool = ..., **kwargs) -> None: ...

class NumberRangeQueryAllOfFrom(_message.Message):
    __slots__ = ("double", "string", "null_value")
    DOUBLE_FIELD_NUMBER: _ClassVar[int]
    STRING_FIELD_NUMBER: _ClassVar[int]
    NULL_VALUE_FIELD_NUMBER: _ClassVar[int]
    double: float
    string: str
    null_value: NullValue
    def __init__(self, double: _Optional[float] = ..., string: _Optional[str] = ..., null_value: _Optional[_Union[NullValue, str]] = ...) -> None: ...

class NumberRangeQueryAllOfTo(_message.Message):
    __slots__ = ("double", "string", "null_value")
    DOUBLE_FIELD_NUMBER: _ClassVar[int]
    STRING_FIELD_NUMBER: _ClassVar[int]
    NULL_VALUE_FIELD_NUMBER: _ClassVar[int]
    double: float
    string: str
    null_value: NullValue
    def __init__(self, double: _Optional[float] = ..., string: _Optional[str] = ..., null_value: _Optional[_Union[NullValue, str]] = ...) -> None: ...

class DateRangeQuery(_message.Message):
    __slots__ = ("field", "boost", "x_name", "relation", "gt", "gte", "lt", "lte", "to", "format", "time_zone", "include_lower", "include_upper")
    FIELD_FIELD_NUMBER: _ClassVar[int]
    BOOST_FIELD_NUMBER: _ClassVar[int]
    X_NAME_FIELD_NUMBER: _ClassVar[int]
    RELATION_FIELD_NUMBER: _ClassVar[int]
    GT_FIELD_NUMBER: _ClassVar[int]
    GTE_FIELD_NUMBER: _ClassVar[int]
    LT_FIELD_NUMBER: _ClassVar[int]
    LTE_FIELD_NUMBER: _ClassVar[int]
    FROM_FIELD_NUMBER: _ClassVar[int]
    TO_FIELD_NUMBER: _ClassVar[int]
    FORMAT_FIELD_NUMBER: _ClassVar[int]
    TIME_ZONE_FIELD_NUMBER: _ClassVar[int]
    INCLUDE_LOWER_FIELD_NUMBER: _ClassVar[int]
    INCLUDE_UPPER_FIELD_NUMBER: _ClassVar[int]
    field: str
    boost: float
    x_name: str
    relation: RangeRelation
    gt: str
    gte: str
    lt: str
    lte: str
    to: DateRangeQueryAllOfTo
    format: str
    time_zone: str
    include_lower: bool
    include_upper: bool
    def __init__(self, field: _Optional[str] = ..., boost: _Optional[float] = ..., x_name: _Optional[str] = ..., relation: _Optional[_Union[RangeRelation, str]] = ..., gt: _Optional[str] = ..., gte: _Optional[str] = ..., lt: _Optional[str] = ..., lte: _Optional[str] = ..., to: _Optional[_Union[DateRangeQueryAllOfTo, _Mapping]] = ..., format: _Optional[str] = ..., time_zone: _Optional[str] = ..., include_lower: bool = ..., include_upper: bool = ..., **kwargs) -> None: ...

class DateRangeQueryAllOfFrom(_message.Message):
    __slots__ = ("string", "null_value")
    STRING_FIELD_NUMBER: _ClassVar[int]
    NULL_VALUE_FIELD_NUMBER: _ClassVar[int]
    string: str
    null_value: NullValue
    def __init__(self, string: _Optional[str] = ..., null_value: _Optional[_Union[NullValue, str]] = ...) -> None: ...

class DateRangeQueryAllOfTo(_message.Message):
    __slots__ = ("string", "null_value")
    STRING_FIELD_NUMBER: _ClassVar[int]
    NULL_VALUE_FIELD_NUMBER: _ClassVar[int]
    string: str
    null_value: NullValue
    def __init__(self, string: _Optional[str] = ..., null_value: _Optional[_Union[NullValue, str]] = ...) -> None: ...

class FuzzyQuery(_message.Message):
    __slots__ = ("field", "value", "boost", "x_name", "max_expansions", "prefix_length", "rewrite_deprecated", "transpositions", "fuzziness", "rewrite")
    FIELD_FIELD_NUMBER: _ClassVar[int]
    VALUE_FIELD_NUMBER: _ClassVar[int]
    BOOST_FIELD_NUMBER: _ClassVar[int]
    X_NAME_FIELD_NUMBER: _ClassVar[int]
    MAX_EXPANSIONS_FIELD_NUMBER: _ClassVar[int]
    PREFIX_LENGTH_FIELD_NUMBER: _ClassVar[int]
    REWRITE_DEPRECATED_FIELD_NUMBER: _ClassVar[int]
    TRANSPOSITIONS_FIELD_NUMBER: _ClassVar[int]
    FUZZINESS_FIELD_NUMBER: _ClassVar[int]
    REWRITE_FIELD_NUMBER: _ClassVar[int]
    field: str
    value: FieldValue
    boost: float
    x_name: str
    max_expansions: int
    prefix_length: int
    rewrite_deprecated: MultiTermQueryRewrite
    transpositions: bool
    fuzziness: Fuzziness
    rewrite: str
    def __init__(self, field: _Optional[str] = ..., value: _Optional[_Union[FieldValue, _Mapping]] = ..., boost: _Optional[float] = ..., x_name: _Optional[str] = ..., max_expansions: _Optional[int] = ..., prefix_length: _Optional[int] = ..., rewrite_deprecated: _Optional[_Union[MultiTermQueryRewrite, str]] = ..., transpositions: bool = ..., fuzziness: _Optional[_Union[Fuzziness, _Mapping]] = ..., rewrite: _Optional[str] = ...) -> None: ...

class Fuzziness(_message.Message):
    __slots__ = ("string", "int32")
    STRING_FIELD_NUMBER: _ClassVar[int]
    INT32_FIELD_NUMBER: _ClassVar[int]
    string: str
    int32: int
    def __init__(self, string: _Optional[str] = ..., int32: _Optional[int] = ...) -> None: ...

class FieldValue(_message.Message):
    __slots__ = ("bool", "general_number", "string", "null_value")
    BOOL_FIELD_NUMBER: _ClassVar[int]
    GENERAL_NUMBER_FIELD_NUMBER: _ClassVar[int]
    STRING_FIELD_NUMBER: _ClassVar[int]
    NULL_VALUE_FIELD_NUMBER: _ClassVar[int]
    bool: bool
    general_number: GeneralNumber
    string: str
    null_value: NullValue
    def __init__(self, bool: bool = ..., general_number: _Optional[_Union[GeneralNumber, _Mapping]] = ..., string: _Optional[str] = ..., null_value: _Optional[_Union[NullValue, str]] = ...) -> None: ...

class IdsQuery(_message.Message):
    __slots__ = ("boost", "x_name", "values")
    BOOST_FIELD_NUMBER: _ClassVar[int]
    X_NAME_FIELD_NUMBER: _ClassVar[int]
    VALUES_FIELD_NUMBER: _ClassVar[int]
    boost: float
    x_name: str
    values: _containers.RepeatedScalarFieldContainer[str]
    def __init__(self, boost: _Optional[float] = ..., x_name: _Optional[str] = ..., values: _Optional[_Iterable[str]] = ...) -> None: ...

class MatchAllQuery(_message.Message):
    __slots__ = ("boost", "x_name")
    BOOST_FIELD_NUMBER: _ClassVar[int]
    X_NAME_FIELD_NUMBER: _ClassVar[int]
    boost: float
    x_name: str
    def __init__(self, boost: _Optional[float] = ..., x_name: _Optional[str] = ...) -> None: ...

class MatchBoolPrefixQuery(_message.Message):
    __slots__ = ("field", "query", "boost", "x_name", "analyzer", "fuzziness", "fuzzy_rewrite_deprecated", "fuzzy_transpositions", "max_expansions", "minimum_should_match", "operator", "prefix_length", "fuzzy_rewrite")
    FIELD_FIELD_NUMBER: _ClassVar[int]
    QUERY_FIELD_NUMBER: _ClassVar[int]
    BOOST_FIELD_NUMBER: _ClassVar[int]
    X_NAME_FIELD_NUMBER: _ClassVar[int]
    ANALYZER_FIELD_NUMBER: _ClassVar[int]
    FUZZINESS_FIELD_NUMBER: _ClassVar[int]
    FUZZY_REWRITE_DEPRECATED_FIELD_NUMBER: _ClassVar[int]
    FUZZY_TRANSPOSITIONS_FIELD_NUMBER: _ClassVar[int]
    MAX_EXPANSIONS_FIELD_NUMBER: _ClassVar[int]
    MINIMUM_SHOULD_MATCH_FIELD_NUMBER: _ClassVar[int]
    OPERATOR_FIELD_NUMBER: _ClassVar[int]
    PREFIX_LENGTH_FIELD_NUMBER: _ClassVar[int]
    FUZZY_REWRITE_FIELD_NUMBER: _ClassVar[int]
    field: str
    query: str
    boost: float
    x_name: str
    analyzer: str
    fuzziness: Fuzziness
    fuzzy_rewrite_deprecated: MultiTermQueryRewrite
    fuzzy_transpositions: bool
    max_expansions: int
    minimum_should_match: MinimumShouldMatch
    operator: Operator
    prefix_length: int
    fuzzy_rewrite: str
    def __init__(self, field: _Optional[str] = ..., query: _Optional[str] = ..., boost: _Optional[float] = ..., x_name: _Optional[str] = ..., analyzer: _Optional[str] = ..., fuzziness: _Optional[_Union[Fuzziness, _Mapping]] = ..., fuzzy_rewrite_deprecated: _Optional[_Union[MultiTermQueryRewrite, str]] = ..., fuzzy_transpositions: bool = ..., max_expansions: _Optional[int] = ..., minimum_should_match: _Optional[_Union[MinimumShouldMatch, _Mapping]] = ..., operator: _Optional[_Union[Operator, str]] = ..., prefix_length: _Optional[int] = ..., fuzzy_rewrite: _Optional[str] = ...) -> None: ...

class MatchNoneQuery(_message.Message):
    __slots__ = ("boost", "x_name")
    BOOST_FIELD_NUMBER: _ClassVar[int]
    X_NAME_FIELD_NUMBER: _ClassVar[int]
    boost: float
    x_name: str
    def __init__(self, boost: _Optional[float] = ..., x_name: _Optional[str] = ...) -> None: ...

class MatchPhrasePrefixQuery(_message.Message):
    __slots__ = ("field", "query", "boost", "x_name", "analyzer", "max_expansions", "slop", "zero_terms_query")
    FIELD_FIELD_NUMBER: _ClassVar[int]
    QUERY_FIELD_NUMBER: _ClassVar[int]
    BOOST_FIELD_NUMBER: _ClassVar[int]
    X_NAME_FIELD_NUMBER: _ClassVar[int]
    ANALYZER_FIELD_NUMBER: _ClassVar[int]
    MAX_EXPANSIONS_FIELD_NUMBER: _ClassVar[int]
    SLOP_FIELD_NUMBER: _ClassVar[int]
    ZERO_TERMS_QUERY_FIELD_NUMBER: _ClassVar[int]
    field: str
    query: str
    boost: float
    x_name: str
    analyzer: str
    max_expansions: int
    slop: int
    zero_terms_query: ZeroTermsQuery
    def __init__(self, field: _Optional[str] = ..., query: _Optional[str] = ..., boost: _Optional[float] = ..., x_name: _Optional[str] = ..., analyzer: _Optional[str] = ..., max_expansions: _Optional[int] = ..., slop: _Optional[int] = ..., zero_terms_query: _Optional[_Union[ZeroTermsQuery, str]] = ...) -> None: ...

class MatchPhraseQuery(_message.Message):
    __slots__ = ("field", "query", "boost", "x_name", "analyzer", "slop", "zero_terms_query")
    FIELD_FIELD_NUMBER: _ClassVar[int]
    QUERY_FIELD_NUMBER: _ClassVar[int]
    BOOST_FIELD_NUMBER: _ClassVar[int]
    X_NAME_FIELD_NUMBER: _ClassVar[int]
    ANALYZER_FIELD_NUMBER: _ClassVar[int]
    SLOP_FIELD_NUMBER: _ClassVar[int]
    ZERO_TERMS_QUERY_FIELD_NUMBER: _ClassVar[int]
    field: str
    query: str
    boost: float
    x_name: str
    analyzer: str
    slop: int
    zero_terms_query: ZeroTermsQuery
    def __init__(self, field: _Optional[str] = ..., query: _Optional[str] = ..., boost: _Optional[float] = ..., x_name: _Optional[str] = ..., analyzer: _Optional[str] = ..., slop: _Optional[int] = ..., zero_terms_query: _Optional[_Union[ZeroTermsQuery, str]] = ...) -> None: ...

class MultiMatchQuery(_message.Message):
    __slots__ = ("query", "boost", "x_name", "analyzer", "auto_generate_synonyms_phrase_query", "fields", "fuzzy_rewrite_deprecated", "fuzziness", "fuzzy_transpositions", "lenient", "max_expansions", "minimum_should_match", "operator", "prefix_length", "slop", "tie_breaker", "type", "zero_terms_query", "fuzzy_rewrite")
    QUERY_FIELD_NUMBER: _ClassVar[int]
    BOOST_FIELD_NUMBER: _ClassVar[int]
    X_NAME_FIELD_NUMBER: _ClassVar[int]
    ANALYZER_FIELD_NUMBER: _ClassVar[int]
    AUTO_GENERATE_SYNONYMS_PHRASE_QUERY_FIELD_NUMBER: _ClassVar[int]
    FIELDS_FIELD_NUMBER: _ClassVar[int]
    FUZZY_REWRITE_DEPRECATED_FIELD_NUMBER: _ClassVar[int]
    FUZZINESS_FIELD_NUMBER: _ClassVar[int]
    FUZZY_TRANSPOSITIONS_FIELD_NUMBER: _ClassVar[int]
    LENIENT_FIELD_NUMBER: _ClassVar[int]
    MAX_EXPANSIONS_FIELD_NUMBER: _ClassVar[int]
    MINIMUM_SHOULD_MATCH_FIELD_NUMBER: _ClassVar[int]
    OPERATOR_FIELD_NUMBER: _ClassVar[int]
    PREFIX_LENGTH_FIELD_NUMBER: _ClassVar[int]
    SLOP_FIELD_NUMBER: _ClassVar[int]
    TIE_BREAKER_FIELD_NUMBER: _ClassVar[int]
    TYPE_FIELD_NUMBER: _ClassVar[int]
    ZERO_TERMS_QUERY_FIELD_NUMBER: _ClassVar[int]
    FUZZY_REWRITE_FIELD_NUMBER: _ClassVar[int]
    query: str
    boost: float
    x_name: str
    analyzer: str
    auto_generate_synonyms_phrase_query: bool
    fields: _containers.RepeatedScalarFieldContainer[str]
    fuzzy_rewrite_deprecated: MultiTermQueryRewrite
    fuzziness: Fuzziness
    fuzzy_transpositions: bool
    lenient: bool
    max_expansions: int
    minimum_should_match: MinimumShouldMatch
    operator: Operator
    prefix_length: int
    slop: int
    tie_breaker: float
    type: TextQueryType
    zero_terms_query: ZeroTermsQuery
    fuzzy_rewrite: str
    def __init__(self, query: _Optional[str] = ..., boost: _Optional[float] = ..., x_name: _Optional[str] = ..., analyzer: _Optional[str] = ..., auto_generate_synonyms_phrase_query: bool = ..., fields: _Optional[_Iterable[str]] = ..., fuzzy_rewrite_deprecated: _Optional[_Union[MultiTermQueryRewrite, str]] = ..., fuzziness: _Optional[_Union[Fuzziness, _Mapping]] = ..., fuzzy_transpositions: bool = ..., lenient: bool = ..., max_expansions: _Optional[int] = ..., minimum_should_match: _Optional[_Union[MinimumShouldMatch, _Mapping]] = ..., operator: _Optional[_Union[Operator, str]] = ..., prefix_length: _Optional[int] = ..., slop: _Optional[int] = ..., tie_breaker: _Optional[float] = ..., type: _Optional[_Union[TextQueryType, str]] = ..., zero_terms_query: _Optional[_Union[ZeroTermsQuery, str]] = ..., fuzzy_rewrite: _Optional[str] = ...) -> None: ...

class FieldValueFactorScoreFunction(_message.Message):
    __slots__ = ("field", "factor", "missing", "modifier")
    FIELD_FIELD_NUMBER: _ClassVar[int]
    FACTOR_FIELD_NUMBER: _ClassVar[int]
    MISSING_FIELD_NUMBER: _ClassVar[int]
    MODIFIER_FIELD_NUMBER: _ClassVar[int]
    field: str
    factor: float
    missing: float
    modifier: FieldValueFactorModifier
    def __init__(self, field: _Optional[str] = ..., factor: _Optional[float] = ..., missing: _Optional[float] = ..., modifier: _Optional[_Union[FieldValueFactorModifier, str]] = ...) -> None: ...

class DoubleMap(_message.Message):
    __slots__ = ("double_map",)
    class DoubleMapEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: float
        def __init__(self, key: _Optional[str] = ..., value: _Optional[float] = ...) -> None: ...
    DOUBLE_MAP_FIELD_NUMBER: _ClassVar[int]
    double_map: _containers.ScalarMap[str, float]
    def __init__(self, double_map: _Optional[_Mapping[str, float]] = ...) -> None: ...

class HitMatchedQueries(_message.Message):
    __slots__ = ("names", "scores")
    NAMES_FIELD_NUMBER: _ClassVar[int]
    SCORES_FIELD_NUMBER: _ClassVar[int]
    names: StringArray
    scores: DoubleMap
    def __init__(self, names: _Optional[_Union[StringArray, _Mapping]] = ..., scores: _Optional[_Union[DoubleMap, _Mapping]] = ...) -> None: ...

class BinaryFieldValue(_message.Message):
    __slots__ = ("bytes_value", "float_array_value", "double_array_value", "int_array_value", "long_array_value")
    BYTES_VALUE_FIELD_NUMBER: _ClassVar[int]
    FLOAT_ARRAY_VALUE_FIELD_NUMBER: _ClassVar[int]
    DOUBLE_ARRAY_VALUE_FIELD_NUMBER: _ClassVar[int]
    INT_ARRAY_VALUE_FIELD_NUMBER: _ClassVar[int]
    LONG_ARRAY_VALUE_FIELD_NUMBER: _ClassVar[int]
    bytes_value: BytesValue
    float_array_value: FloatArrayValue
    double_array_value: DoubleArrayValue
    int_array_value: IntArrayValue
    long_array_value: LongArrayValue
    def __init__(self, bytes_value: _Optional[_Union[BytesValue, _Mapping]] = ..., float_array_value: _Optional[_Union[FloatArrayValue, _Mapping]] = ..., double_array_value: _Optional[_Union[DoubleArrayValue, _Mapping]] = ..., int_array_value: _Optional[_Union[IntArrayValue, _Mapping]] = ..., long_array_value: _Optional[_Union[LongArrayValue, _Mapping]] = ...) -> None: ...

class BytesValue(_message.Message):
    __slots__ = ("bytes",)
    BYTES_FIELD_NUMBER: _ClassVar[int]
    bytes: bytes
    def __init__(self, bytes: _Optional[bytes] = ...) -> None: ...

class FloatArrayValue(_message.Message):
    __slots__ = ("binary_le", "values")
    BINARY_LE_FIELD_NUMBER: _ClassVar[int]
    VALUES_FIELD_NUMBER: _ClassVar[int]
    binary_le: FloatBinaryLE
    values: FloatList
    def __init__(self, binary_le: _Optional[_Union[FloatBinaryLE, _Mapping]] = ..., values: _Optional[_Union[FloatList, _Mapping]] = ...) -> None: ...

class FloatBinaryLE(_message.Message):
    __slots__ = ("bytes_le", "dimension")
    BYTES_LE_FIELD_NUMBER: _ClassVar[int]
    DIMENSION_FIELD_NUMBER: _ClassVar[int]
    bytes_le: bytes
    dimension: int
    def __init__(self, bytes_le: _Optional[bytes] = ..., dimension: _Optional[int] = ...) -> None: ...

class FloatList(_message.Message):
    __slots__ = ("values",)
    VALUES_FIELD_NUMBER: _ClassVar[int]
    values: _containers.RepeatedScalarFieldContainer[float]
    def __init__(self, values: _Optional[_Iterable[float]] = ...) -> None: ...

class DoubleArrayValue(_message.Message):
    __slots__ = ("binary_le", "values")
    BINARY_LE_FIELD_NUMBER: _ClassVar[int]
    VALUES_FIELD_NUMBER: _ClassVar[int]
    binary_le: DoubleBinaryLE
    values: DoubleList
    def __init__(self, binary_le: _Optional[_Union[DoubleBinaryLE, _Mapping]] = ..., values: _Optional[_Union[DoubleList, _Mapping]] = ...) -> None: ...

class DoubleBinaryLE(_message.Message):
    __slots__ = ("bytes_le", "dimension")
    BYTES_LE_FIELD_NUMBER: _ClassVar[int]
    DIMENSION_FIELD_NUMBER: _ClassVar[int]
    bytes_le: bytes
    dimension: int
    def __init__(self, bytes_le: _Optional[bytes] = ..., dimension: _Optional[int] = ...) -> None: ...

class DoubleList(_message.Message):
    __slots__ = ("values",)
    VALUES_FIELD_NUMBER: _ClassVar[int]
    values: _containers.RepeatedScalarFieldContainer[float]
    def __init__(self, values: _Optional[_Iterable[float]] = ...) -> None: ...

class IntArrayValue(_message.Message):
    __slots__ = ("binary_le", "values")
    BINARY_LE_FIELD_NUMBER: _ClassVar[int]
    VALUES_FIELD_NUMBER: _ClassVar[int]
    binary_le: IntBinaryLE
    values: IntList
    def __init__(self, binary_le: _Optional[_Union[IntBinaryLE, _Mapping]] = ..., values: _Optional[_Union[IntList, _Mapping]] = ...) -> None: ...

class IntBinaryLE(_message.Message):
    __slots__ = ("bytes_le", "dimension")
    BYTES_LE_FIELD_NUMBER: _ClassVar[int]
    DIMENSION_FIELD_NUMBER: _ClassVar[int]
    bytes_le: bytes
    dimension: int
    def __init__(self, bytes_le: _Optional[bytes] = ..., dimension: _Optional[int] = ...) -> None: ...

class IntList(_message.Message):
    __slots__ = ("values",)
    VALUES_FIELD_NUMBER: _ClassVar[int]
    values: _containers.RepeatedScalarFieldContainer[int]
    def __init__(self, values: _Optional[_Iterable[int]] = ...) -> None: ...

class LongArrayValue(_message.Message):
    __slots__ = ("binary_le", "values")
    BINARY_LE_FIELD_NUMBER: _ClassVar[int]
    VALUES_FIELD_NUMBER: _ClassVar[int]
    binary_le: LongBinaryLE
    values: LongList
    def __init__(self, binary_le: _Optional[_Union[LongBinaryLE, _Mapping]] = ..., values: _Optional[_Union[LongList, _Mapping]] = ...) -> None: ...

class LongBinaryLE(_message.Message):
    __slots__ = ("bytes_le", "dimension")
    BYTES_LE_FIELD_NUMBER: _ClassVar[int]
    DIMENSION_FIELD_NUMBER: _ClassVar[int]
    bytes_le: bytes
    dimension: int
    def __init__(self, bytes_le: _Optional[bytes] = ..., dimension: _Optional[int] = ...) -> None: ...

class LongList(_message.Message):
    __slots__ = ("values",)
    VALUES_FIELD_NUMBER: _ClassVar[int]
    values: _containers.RepeatedScalarFieldContainer[int]
    def __init__(self, values: _Optional[_Iterable[int]] = ...) -> None: ...

class ShardSearchFailure(_message.Message):
    __slots__ = ("shard", "index", "node", "reason")
    SHARD_FIELD_NUMBER: _ClassVar[int]
    INDEX_FIELD_NUMBER: _ClassVar[int]
    NODE_FIELD_NUMBER: _ClassVar[int]
    REASON_FIELD_NUMBER: _ClassVar[int]
    shard: int
    index: str
    node: str
    reason: ErrorCause
    def __init__(self, shard: _Optional[int] = ..., index: _Optional[str] = ..., node: _Optional[str] = ..., reason: _Optional[_Union[ErrorCause, _Mapping]] = ...) -> None: ...

class FloatMap(_message.Message):
    __slots__ = ("float_map",)
    class FloatMapEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: float
        def __init__(self, key: _Optional[str] = ..., value: _Optional[float] = ...) -> None: ...
    FLOAT_MAP_FIELD_NUMBER: _ClassVar[int]
    float_map: _containers.ScalarMap[str, float]
    def __init__(self, float_map: _Optional[_Mapping[str, float]] = ...) -> None: ...

class Aggregate(_message.Message):
    __slots__ = ("dterms", "lterms", "max", "min", "sterms", "ulterms", "umterms")
    DTERMS_FIELD_NUMBER: _ClassVar[int]
    LTERMS_FIELD_NUMBER: _ClassVar[int]
    MAX_FIELD_NUMBER: _ClassVar[int]
    MIN_FIELD_NUMBER: _ClassVar[int]
    STERMS_FIELD_NUMBER: _ClassVar[int]
    ULTERMS_FIELD_NUMBER: _ClassVar[int]
    UMTERMS_FIELD_NUMBER: _ClassVar[int]
    dterms: DoubleTermsAggregate
    lterms: LongTermsAggregate
    max: SingleMetricAggregateBase
    min: SingleMetricAggregateBase
    sterms: StringTermsAggregate
    ulterms: UnsignedLongTermsAggregate
    umterms: UnmappedTermsAggregate
    def __init__(self, dterms: _Optional[_Union[DoubleTermsAggregate, _Mapping]] = ..., lterms: _Optional[_Union[LongTermsAggregate, _Mapping]] = ..., max: _Optional[_Union[SingleMetricAggregateBase, _Mapping]] = ..., min: _Optional[_Union[SingleMetricAggregateBase, _Mapping]] = ..., sterms: _Optional[_Union[StringTermsAggregate, _Mapping]] = ..., ulterms: _Optional[_Union[UnsignedLongTermsAggregate, _Mapping]] = ..., umterms: _Optional[_Union[UnmappedTermsAggregate, _Mapping]] = ...) -> None: ...

class AggregationContainer(_message.Message):
    __slots__ = ("meta", "max", "min", "terms_aggregation")
    META_FIELD_NUMBER: _ClassVar[int]
    MAX_FIELD_NUMBER: _ClassVar[int]
    MIN_FIELD_NUMBER: _ClassVar[int]
    TERMS_AGGREGATION_FIELD_NUMBER: _ClassVar[int]
    meta: ObjectMap
    max: MaxAggregation
    min: MinAggregation
    terms_aggregation: TermsAggregation
    def __init__(self, meta: _Optional[_Union[ObjectMap, _Mapping]] = ..., max: _Optional[_Union[MaxAggregation, _Mapping]] = ..., min: _Optional[_Union[MinAggregation, _Mapping]] = ..., terms_aggregation: _Optional[_Union[TermsAggregation, _Mapping]] = ...) -> None: ...

class DoubleTermsAggregate(_message.Message):
    __slots__ = ("meta", "buckets", "doc_count_error_upper_bound", "sum_other_doc_count")
    META_FIELD_NUMBER: _ClassVar[int]
    BUCKETS_FIELD_NUMBER: _ClassVar[int]
    DOC_COUNT_ERROR_UPPER_BOUND_FIELD_NUMBER: _ClassVar[int]
    SUM_OTHER_DOC_COUNT_FIELD_NUMBER: _ClassVar[int]
    meta: ObjectMap
    buckets: _containers.RepeatedCompositeFieldContainer[DoubleTermsBucket]
    doc_count_error_upper_bound: int
    sum_other_doc_count: int
    def __init__(self, meta: _Optional[_Union[ObjectMap, _Mapping]] = ..., buckets: _Optional[_Iterable[_Union[DoubleTermsBucket, _Mapping]]] = ..., doc_count_error_upper_bound: _Optional[int] = ..., sum_other_doc_count: _Optional[int] = ...) -> None: ...

class DoubleTermsBucket(_message.Message):
    __slots__ = ("doc_count", "aggregate", "doc_count_error_upper_bound", "key", "key_as_string")
    class AggregateEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: Aggregate
        def __init__(self, key: _Optional[str] = ..., value: _Optional[_Union[Aggregate, _Mapping]] = ...) -> None: ...
    DOC_COUNT_FIELD_NUMBER: _ClassVar[int]
    AGGREGATE_FIELD_NUMBER: _ClassVar[int]
    DOC_COUNT_ERROR_UPPER_BOUND_FIELD_NUMBER: _ClassVar[int]
    KEY_FIELD_NUMBER: _ClassVar[int]
    KEY_AS_STRING_FIELD_NUMBER: _ClassVar[int]
    doc_count: int
    aggregate: _containers.MessageMap[str, Aggregate]
    doc_count_error_upper_bound: int
    key: float
    key_as_string: str
    def __init__(self, doc_count: _Optional[int] = ..., aggregate: _Optional[_Mapping[str, Aggregate]] = ..., doc_count_error_upper_bound: _Optional[int] = ..., key: _Optional[float] = ..., key_as_string: _Optional[str] = ...) -> None: ...

class LongTermsAggregate(_message.Message):
    __slots__ = ("meta", "buckets", "doc_count_error_upper_bound", "sum_other_doc_count")
    META_FIELD_NUMBER: _ClassVar[int]
    BUCKETS_FIELD_NUMBER: _ClassVar[int]
    DOC_COUNT_ERROR_UPPER_BOUND_FIELD_NUMBER: _ClassVar[int]
    SUM_OTHER_DOC_COUNT_FIELD_NUMBER: _ClassVar[int]
    meta: ObjectMap
    buckets: _containers.RepeatedCompositeFieldContainer[LongTermsBucket]
    doc_count_error_upper_bound: int
    sum_other_doc_count: int
    def __init__(self, meta: _Optional[_Union[ObjectMap, _Mapping]] = ..., buckets: _Optional[_Iterable[_Union[LongTermsBucket, _Mapping]]] = ..., doc_count_error_upper_bound: _Optional[int] = ..., sum_other_doc_count: _Optional[int] = ...) -> None: ...

class LongTermsBucket(_message.Message):
    __slots__ = ("doc_count", "aggregate", "doc_count_error_upper_bound", "key", "key_as_string")
    class AggregateEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: Aggregate
        def __init__(self, key: _Optional[str] = ..., value: _Optional[_Union[Aggregate, _Mapping]] = ...) -> None: ...
    DOC_COUNT_FIELD_NUMBER: _ClassVar[int]
    AGGREGATE_FIELD_NUMBER: _ClassVar[int]
    DOC_COUNT_ERROR_UPPER_BOUND_FIELD_NUMBER: _ClassVar[int]
    KEY_FIELD_NUMBER: _ClassVar[int]
    KEY_AS_STRING_FIELD_NUMBER: _ClassVar[int]
    doc_count: int
    aggregate: _containers.MessageMap[str, Aggregate]
    doc_count_error_upper_bound: int
    key: LongTermsBucketKey
    key_as_string: str
    def __init__(self, doc_count: _Optional[int] = ..., aggregate: _Optional[_Mapping[str, Aggregate]] = ..., doc_count_error_upper_bound: _Optional[int] = ..., key: _Optional[_Union[LongTermsBucketKey, _Mapping]] = ..., key_as_string: _Optional[str] = ...) -> None: ...

class LongTermsBucketKey(_message.Message):
    __slots__ = ("signed", "unsigned")
    SIGNED_FIELD_NUMBER: _ClassVar[int]
    UNSIGNED_FIELD_NUMBER: _ClassVar[int]
    signed: int
    unsigned: str
    def __init__(self, signed: _Optional[int] = ..., unsigned: _Optional[str] = ...) -> None: ...

class MaxAggregation(_message.Message):
    __slots__ = ("missing", "field", "script", "format", "value_type")
    MISSING_FIELD_NUMBER: _ClassVar[int]
    FIELD_FIELD_NUMBER: _ClassVar[int]
    SCRIPT_FIELD_NUMBER: _ClassVar[int]
    FORMAT_FIELD_NUMBER: _ClassVar[int]
    VALUE_TYPE_FIELD_NUMBER: _ClassVar[int]
    missing: FieldValue
    field: str
    script: Script
    format: str
    value_type: ValueType
    def __init__(self, missing: _Optional[_Union[FieldValue, _Mapping]] = ..., field: _Optional[str] = ..., script: _Optional[_Union[Script, _Mapping]] = ..., format: _Optional[str] = ..., value_type: _Optional[_Union[ValueType, str]] = ...) -> None: ...

class MinAggregation(_message.Message):
    __slots__ = ("missing", "field", "script", "format", "value_type")
    MISSING_FIELD_NUMBER: _ClassVar[int]
    FIELD_FIELD_NUMBER: _ClassVar[int]
    SCRIPT_FIELD_NUMBER: _ClassVar[int]
    FORMAT_FIELD_NUMBER: _ClassVar[int]
    VALUE_TYPE_FIELD_NUMBER: _ClassVar[int]
    missing: FieldValue
    field: str
    script: Script
    format: str
    value_type: ValueType
    def __init__(self, missing: _Optional[_Union[FieldValue, _Mapping]] = ..., field: _Optional[str] = ..., script: _Optional[_Union[Script, _Mapping]] = ..., format: _Optional[str] = ..., value_type: _Optional[_Union[ValueType, str]] = ...) -> None: ...

class SingleMetricAggregateBase(_message.Message):
    __slots__ = ("meta", "value", "value_as_string")
    META_FIELD_NUMBER: _ClassVar[int]
    VALUE_FIELD_NUMBER: _ClassVar[int]
    VALUE_AS_STRING_FIELD_NUMBER: _ClassVar[int]
    meta: ObjectMap
    value: SingleMetricAggregateBaseAllOfValue
    value_as_string: str
    def __init__(self, meta: _Optional[_Union[ObjectMap, _Mapping]] = ..., value: _Optional[_Union[SingleMetricAggregateBaseAllOfValue, _Mapping]] = ..., value_as_string: _Optional[str] = ...) -> None: ...

class SingleMetricAggregateBaseAllOfValue(_message.Message):
    __slots__ = ("double", "null_value")
    DOUBLE_FIELD_NUMBER: _ClassVar[int]
    NULL_VALUE_FIELD_NUMBER: _ClassVar[int]
    double: float
    null_value: NullValue
    def __init__(self, double: _Optional[float] = ..., null_value: _Optional[_Union[NullValue, str]] = ...) -> None: ...

class SortOrderSingleMap(_message.Message):
    __slots__ = ("field", "sort_order")
    FIELD_FIELD_NUMBER: _ClassVar[int]
    SORT_ORDER_FIELD_NUMBER: _ClassVar[int]
    field: str
    sort_order: SortOrder
    def __init__(self, field: _Optional[str] = ..., sort_order: _Optional[_Union[SortOrder, str]] = ...) -> None: ...

class StringTermsAggregate(_message.Message):
    __slots__ = ("meta", "buckets", "doc_count_error_upper_bound", "sum_other_doc_count")
    META_FIELD_NUMBER: _ClassVar[int]
    BUCKETS_FIELD_NUMBER: _ClassVar[int]
    DOC_COUNT_ERROR_UPPER_BOUND_FIELD_NUMBER: _ClassVar[int]
    SUM_OTHER_DOC_COUNT_FIELD_NUMBER: _ClassVar[int]
    meta: ObjectMap
    buckets: _containers.RepeatedCompositeFieldContainer[StringTermsBucket]
    doc_count_error_upper_bound: int
    sum_other_doc_count: int
    def __init__(self, meta: _Optional[_Union[ObjectMap, _Mapping]] = ..., buckets: _Optional[_Iterable[_Union[StringTermsBucket, _Mapping]]] = ..., doc_count_error_upper_bound: _Optional[int] = ..., sum_other_doc_count: _Optional[int] = ...) -> None: ...

class StringTermsBucket(_message.Message):
    __slots__ = ("doc_count", "aggregate", "doc_count_error_upper_bound", "key")
    class AggregateEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: Aggregate
        def __init__(self, key: _Optional[str] = ..., value: _Optional[_Union[Aggregate, _Mapping]] = ...) -> None: ...
    DOC_COUNT_FIELD_NUMBER: _ClassVar[int]
    AGGREGATE_FIELD_NUMBER: _ClassVar[int]
    DOC_COUNT_ERROR_UPPER_BOUND_FIELD_NUMBER: _ClassVar[int]
    KEY_FIELD_NUMBER: _ClassVar[int]
    doc_count: int
    aggregate: _containers.MessageMap[str, Aggregate]
    doc_count_error_upper_bound: int
    key: str
    def __init__(self, doc_count: _Optional[int] = ..., aggregate: _Optional[_Mapping[str, Aggregate]] = ..., doc_count_error_upper_bound: _Optional[int] = ..., key: _Optional[str] = ...) -> None: ...

class TermsAggregation(_message.Message):
    __slots__ = ("aggregations", "terms")
    class AggregationsEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: AggregationContainer
        def __init__(self, key: _Optional[str] = ..., value: _Optional[_Union[AggregationContainer, _Mapping]] = ...) -> None: ...
    AGGREGATIONS_FIELD_NUMBER: _ClassVar[int]
    TERMS_FIELD_NUMBER: _ClassVar[int]
    aggregations: _containers.MessageMap[str, AggregationContainer]
    terms: TermsAggregationFields
    def __init__(self, aggregations: _Optional[_Mapping[str, AggregationContainer]] = ..., terms: _Optional[_Union[TermsAggregationFields, _Mapping]] = ...) -> None: ...

class TermsAggregationFields(_message.Message):
    __slots__ = ("collect_mode", "exclude", "execution_hint", "include", "min_doc_count", "missing", "value_type", "order", "shard_size", "shard_min_doc_count", "show_term_doc_count_error", "size", "format", "field", "script")
    COLLECT_MODE_FIELD_NUMBER: _ClassVar[int]
    EXCLUDE_FIELD_NUMBER: _ClassVar[int]
    EXECUTION_HINT_FIELD_NUMBER: _ClassVar[int]
    INCLUDE_FIELD_NUMBER: _ClassVar[int]
    MIN_DOC_COUNT_FIELD_NUMBER: _ClassVar[int]
    MISSING_FIELD_NUMBER: _ClassVar[int]
    VALUE_TYPE_FIELD_NUMBER: _ClassVar[int]
    ORDER_FIELD_NUMBER: _ClassVar[int]
    SHARD_SIZE_FIELD_NUMBER: _ClassVar[int]
    SHARD_MIN_DOC_COUNT_FIELD_NUMBER: _ClassVar[int]
    SHOW_TERM_DOC_COUNT_ERROR_FIELD_NUMBER: _ClassVar[int]
    SIZE_FIELD_NUMBER: _ClassVar[int]
    FORMAT_FIELD_NUMBER: _ClassVar[int]
    FIELD_FIELD_NUMBER: _ClassVar[int]
    SCRIPT_FIELD_NUMBER: _ClassVar[int]
    collect_mode: TermsAggregationCollectMode
    exclude: TermsExclude
    execution_hint: TermsAggregationExecutionHint
    include: TermsInclude
    min_doc_count: int
    missing: FieldValue
    value_type: ValueType
    order: _containers.RepeatedCompositeFieldContainer[SortOrderSingleMap]
    shard_size: int
    shard_min_doc_count: int
    show_term_doc_count_error: bool
    size: int
    format: str
    field: str
    script: Script
    def __init__(self, collect_mode: _Optional[_Union[TermsAggregationCollectMode, str]] = ..., exclude: _Optional[_Union[TermsExclude, _Mapping]] = ..., execution_hint: _Optional[_Union[TermsAggregationExecutionHint, str]] = ..., include: _Optional[_Union[TermsInclude, _Mapping]] = ..., min_doc_count: _Optional[int] = ..., missing: _Optional[_Union[FieldValue, _Mapping]] = ..., value_type: _Optional[_Union[ValueType, str]] = ..., order: _Optional[_Iterable[_Union[SortOrderSingleMap, _Mapping]]] = ..., shard_size: _Optional[int] = ..., shard_min_doc_count: _Optional[int] = ..., show_term_doc_count_error: bool = ..., size: _Optional[int] = ..., format: _Optional[str] = ..., field: _Optional[str] = ..., script: _Optional[_Union[Script, _Mapping]] = ...) -> None: ...

class TermsExclude(_message.Message):
    __slots__ = ("regexp", "terms")
    REGEXP_FIELD_NUMBER: _ClassVar[int]
    TERMS_FIELD_NUMBER: _ClassVar[int]
    regexp: str
    terms: StringArray
    def __init__(self, regexp: _Optional[str] = ..., terms: _Optional[_Union[StringArray, _Mapping]] = ...) -> None: ...

class TermsInclude(_message.Message):
    __slots__ = ("regexp", "terms", "partition")
    REGEXP_FIELD_NUMBER: _ClassVar[int]
    TERMS_FIELD_NUMBER: _ClassVar[int]
    PARTITION_FIELD_NUMBER: _ClassVar[int]
    regexp: str
    terms: StringArray
    partition: TermsPartition
    def __init__(self, regexp: _Optional[str] = ..., terms: _Optional[_Union[StringArray, _Mapping]] = ..., partition: _Optional[_Union[TermsPartition, _Mapping]] = ...) -> None: ...

class TermsPartition(_message.Message):
    __slots__ = ("num_partitions", "partition")
    NUM_PARTITIONS_FIELD_NUMBER: _ClassVar[int]
    PARTITION_FIELD_NUMBER: _ClassVar[int]
    num_partitions: int
    partition: int
    def __init__(self, num_partitions: _Optional[int] = ..., partition: _Optional[int] = ...) -> None: ...

class UnmappedTermsAggregate(_message.Message):
    __slots__ = ("meta", "buckets", "doc_count_error_upper_bound", "sum_other_doc_count")
    META_FIELD_NUMBER: _ClassVar[int]
    BUCKETS_FIELD_NUMBER: _ClassVar[int]
    DOC_COUNT_ERROR_UPPER_BOUND_FIELD_NUMBER: _ClassVar[int]
    SUM_OTHER_DOC_COUNT_FIELD_NUMBER: _ClassVar[int]
    meta: ObjectMap
    buckets: _containers.RepeatedCompositeFieldContainer[ObjectMap]
    doc_count_error_upper_bound: int
    sum_other_doc_count: int
    def __init__(self, meta: _Optional[_Union[ObjectMap, _Mapping]] = ..., buckets: _Optional[_Iterable[_Union[ObjectMap, _Mapping]]] = ..., doc_count_error_upper_bound: _Optional[int] = ..., sum_other_doc_count: _Optional[int] = ...) -> None: ...

class UnsignedLongTermsAggregate(_message.Message):
    __slots__ = ("meta", "buckets", "doc_count_error_upper_bound", "sum_other_doc_count")
    META_FIELD_NUMBER: _ClassVar[int]
    BUCKETS_FIELD_NUMBER: _ClassVar[int]
    DOC_COUNT_ERROR_UPPER_BOUND_FIELD_NUMBER: _ClassVar[int]
    SUM_OTHER_DOC_COUNT_FIELD_NUMBER: _ClassVar[int]
    meta: ObjectMap
    buckets: _containers.RepeatedCompositeFieldContainer[UnsignedLongTermsBucket]
    doc_count_error_upper_bound: int
    sum_other_doc_count: int
    def __init__(self, meta: _Optional[_Union[ObjectMap, _Mapping]] = ..., buckets: _Optional[_Iterable[_Union[UnsignedLongTermsBucket, _Mapping]]] = ..., doc_count_error_upper_bound: _Optional[int] = ..., sum_other_doc_count: _Optional[int] = ...) -> None: ...

class UnsignedLongTermsBucket(_message.Message):
    __slots__ = ("doc_count", "aggregate", "doc_count_error_upper_bound", "key", "key_as_string")
    class AggregateEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: Aggregate
        def __init__(self, key: _Optional[str] = ..., value: _Optional[_Union[Aggregate, _Mapping]] = ...) -> None: ...
    DOC_COUNT_FIELD_NUMBER: _ClassVar[int]
    AGGREGATE_FIELD_NUMBER: _ClassVar[int]
    DOC_COUNT_ERROR_UPPER_BOUND_FIELD_NUMBER: _ClassVar[int]
    KEY_FIELD_NUMBER: _ClassVar[int]
    KEY_AS_STRING_FIELD_NUMBER: _ClassVar[int]
    doc_count: int
    aggregate: _containers.MessageMap[str, Aggregate]
    doc_count_error_upper_bound: int
    key: int
    key_as_string: str
    def __init__(self, doc_count: _Optional[int] = ..., aggregate: _Optional[_Mapping[str, Aggregate]] = ..., doc_count_error_upper_bound: _Optional[int] = ..., key: _Optional[int] = ..., key_as_string: _Optional[str] = ...) -> None: ...

class ByteBuffer(_message.Message):
    __slots__ = ("array", "order")
    ARRAY_FIELD_NUMBER: _ClassVar[int]
    ORDER_FIELD_NUMBER: _ClassVar[int]
    array: str
    order: ByteOrder
    def __init__(self, array: _Optional[str] = ..., order: _Optional[_Union[ByteOrder, str]] = ...) -> None: ...

class ColumnMeta(_message.Message):
    __slots__ = ("name", "column_type")
    NAME_FIELD_NUMBER: _ClassVar[int]
    COLUMN_TYPE_FIELD_NUMBER: _ClassVar[int]
    name: str
    column_type: ColumnType
    def __init__(self, name: _Optional[str] = ..., column_type: _Optional[_Union[ColumnType, str]] = ...) -> None: ...

class DataAsMap(_message.Message):
    __slots__ = ("content", "is_last")
    CONTENT_FIELD_NUMBER: _ClassVar[int]
    IS_LAST_FIELD_NUMBER: _ClassVar[int]
    content: str
    is_last: bool
    def __init__(self, content: _Optional[str] = ..., is_last: bool = ...) -> None: ...

class InferenceResults(_message.Message):
    __slots__ = ("output",)
    OUTPUT_FIELD_NUMBER: _ClassVar[int]
    output: _containers.RepeatedCompositeFieldContainer[Output]
    def __init__(self, output: _Optional[_Iterable[_Union[Output, _Mapping]]] = ...) -> None: ...

class MLExecuteAgentStreamRequestBody(_message.Message):
    __slots__ = ("parameters",)
    PARAMETERS_FIELD_NUMBER: _ClassVar[int]
    parameters: Parameters
    def __init__(self, parameters: _Optional[_Union[Parameters, _Mapping]] = ...) -> None: ...

class MLPredictModelStreamRequestBody(_message.Message):
    __slots__ = ("parameters",)
    PARAMETERS_FIELD_NUMBER: _ClassVar[int]
    parameters: Parameters
    def __init__(self, parameters: _Optional[_Union[Parameters, _Mapping]] = ...) -> None: ...

class Messages(_message.Message):
    __slots__ = ("role", "content")
    ROLE_FIELD_NUMBER: _ClassVar[int]
    CONTENT_FIELD_NUMBER: _ClassVar[int]
    role: str
    content: str
    def __init__(self, role: _Optional[str] = ..., content: _Optional[str] = ...) -> None: ...

class Output(_message.Message):
    __slots__ = ("name", "data_type", "shape", "data", "byte_buffer", "result", "data_as_map")
    NAME_FIELD_NUMBER: _ClassVar[int]
    DATA_TYPE_FIELD_NUMBER: _ClassVar[int]
    SHAPE_FIELD_NUMBER: _ClassVar[int]
    DATA_FIELD_NUMBER: _ClassVar[int]
    BYTE_BUFFER_FIELD_NUMBER: _ClassVar[int]
    RESULT_FIELD_NUMBER: _ClassVar[int]
    DATA_AS_MAP_FIELD_NUMBER: _ClassVar[int]
    name: str
    data_type: MlResultDataType
    shape: _containers.RepeatedScalarFieldContainer[int]
    data: _containers.RepeatedScalarFieldContainer[float]
    byte_buffer: ByteBuffer
    result: str
    data_as_map: DataAsMap
    def __init__(self, name: _Optional[str] = ..., data_type: _Optional[_Union[MlResultDataType, str]] = ..., shape: _Optional[_Iterable[int]] = ..., data: _Optional[_Iterable[float]] = ..., byte_buffer: _Optional[_Union[ByteBuffer, _Mapping]] = ..., result: _Optional[str] = ..., data_as_map: _Optional[_Union[DataAsMap, _Mapping]] = ...) -> None: ...

class Parameters(_message.Message):
    __slots__ = ("messages", "inputs", "question", "x_llm_interface")
    MESSAGES_FIELD_NUMBER: _ClassVar[int]
    INPUTS_FIELD_NUMBER: _ClassVar[int]
    QUESTION_FIELD_NUMBER: _ClassVar[int]
    X_LLM_INTERFACE_FIELD_NUMBER: _ClassVar[int]
    messages: _containers.RepeatedCompositeFieldContainer[Messages]
    inputs: str
    question: str
    x_llm_interface: str
    def __init__(self, messages: _Optional[_Iterable[_Union[Messages, _Mapping]]] = ..., inputs: _Optional[str] = ..., question: _Optional[str] = ..., x_llm_interface: _Optional[str] = ...) -> None: ...

class PredictResponse(_message.Message):
    __slots__ = ("inference_results", "status", "prediction_result")
    INFERENCE_RESULTS_FIELD_NUMBER: _ClassVar[int]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    PREDICTION_RESULT_FIELD_NUMBER: _ClassVar[int]
    inference_results: _containers.RepeatedCompositeFieldContainer[InferenceResults]
    status: Status
    prediction_result: PredictionResult
    def __init__(self, inference_results: _Optional[_Iterable[_Union[InferenceResults, _Mapping]]] = ..., status: _Optional[_Union[Status, str]] = ..., prediction_result: _Optional[_Union[PredictionResult, _Mapping]] = ...) -> None: ...

class PredictionResult(_message.Message):
    __slots__ = ("column_metas", "rows")
    COLUMN_METAS_FIELD_NUMBER: _ClassVar[int]
    ROWS_FIELD_NUMBER: _ClassVar[int]
    column_metas: _containers.RepeatedCompositeFieldContainer[ColumnMeta]
    rows: _containers.RepeatedCompositeFieldContainer[Rows]
    def __init__(self, column_metas: _Optional[_Iterable[_Union[ColumnMeta, _Mapping]]] = ..., rows: _Optional[_Iterable[_Union[Rows, _Mapping]]] = ...) -> None: ...

class Rows(_message.Message):
    __slots__ = ("values",)
    VALUES_FIELD_NUMBER: _ClassVar[int]
    values: _containers.RepeatedCompositeFieldContainer[Values]
    def __init__(self, values: _Optional[_Iterable[_Union[Values, _Mapping]]] = ...) -> None: ...

class Values(_message.Message):
    __slots__ = ("column_type", "value")
    COLUMN_TYPE_FIELD_NUMBER: _ClassVar[int]
    VALUE_FIELD_NUMBER: _ClassVar[int]
    column_type: ColumnType
    value: GeneralNumber
    def __init__(self, column_type: _Optional[_Union[ColumnType, str]] = ..., value: _Optional[_Union[GeneralNumber, _Mapping]] = ...) -> None: ...

class MlExecuteAgentStreamRequest(_message.Message):
    __slots__ = ("agent_id", "global_params", "ml_execute_agent_stream_request_body")
    AGENT_ID_FIELD_NUMBER: _ClassVar[int]
    GLOBAL_PARAMS_FIELD_NUMBER: _ClassVar[int]
    ML_EXECUTE_AGENT_STREAM_REQUEST_BODY_FIELD_NUMBER: _ClassVar[int]
    agent_id: str
    global_params: GlobalParams
    ml_execute_agent_stream_request_body: MLExecuteAgentStreamRequestBody
    def __init__(self, agent_id: _Optional[str] = ..., global_params: _Optional[_Union[GlobalParams, _Mapping]] = ..., ml_execute_agent_stream_request_body: _Optional[_Union[MLExecuteAgentStreamRequestBody, _Mapping]] = ...) -> None: ...

class MlPredictModelStreamRequest(_message.Message):
    __slots__ = ("model_id", "global_params", "ml_predict_model_stream_request_body")
    MODEL_ID_FIELD_NUMBER: _ClassVar[int]
    GLOBAL_PARAMS_FIELD_NUMBER: _ClassVar[int]
    ML_PREDICT_MODEL_STREAM_REQUEST_BODY_FIELD_NUMBER: _ClassVar[int]
    model_id: str
    global_params: GlobalParams
    ml_predict_model_stream_request_body: MLPredictModelStreamRequestBody
    def __init__(self, model_id: _Optional[str] = ..., global_params: _Optional[_Union[GlobalParams, _Mapping]] = ..., ml_predict_model_stream_request_body: _Optional[_Union[MLPredictModelStreamRequestBody, _Mapping]] = ...) -> None: ...

class CreatePITResponse(_message.Message):
    __slots__ = ("pit_id", "creation_time", "x_shards")
    PIT_ID_FIELD_NUMBER: _ClassVar[int]
    CREATION_TIME_FIELD_NUMBER: _ClassVar[int]
    X_SHARDS_FIELD_NUMBER: _ClassVar[int]
    pit_id: str
    creation_time: int
    x_shards: ShardStatistics
    def __init__(self, pit_id: _Optional[str] = ..., creation_time: _Optional[int] = ..., x_shards: _Optional[_Union[ShardStatistics, _Mapping]] = ...) -> None: ...

class DeletePITResponse(_message.Message):
    __slots__ = ("pits",)
    PITS_FIELD_NUMBER: _ClassVar[int]
    pits: _containers.RepeatedCompositeFieldContainer[DeletedPit]
    def __init__(self, pits: _Optional[_Iterable[_Union[DeletedPit, _Mapping]]] = ...) -> None: ...

class DeletePitRequest(_message.Message):
    __slots__ = ("pit_id",)
    PIT_ID_FIELD_NUMBER: _ClassVar[int]
    pit_id: _containers.RepeatedScalarFieldContainer[str]
    def __init__(self, pit_id: _Optional[_Iterable[str]] = ...) -> None: ...

class DeletedPit(_message.Message):
    __slots__ = ("pit_id", "successful")
    PIT_ID_FIELD_NUMBER: _ClassVar[int]
    SUCCESSFUL_FIELD_NUMBER: _ClassVar[int]
    pit_id: str
    successful: bool
    def __init__(self, pit_id: _Optional[str] = ..., successful: bool = ...) -> None: ...

class CreatePitRequest(_message.Message):
    __slots__ = ("index", "keep_alive", "allow_no_indices", "allow_partial_pit_creation", "expand_wildcards", "ignore_throttled", "ignore_unavailable", "preference", "routing", "global_params")
    INDEX_FIELD_NUMBER: _ClassVar[int]
    KEEP_ALIVE_FIELD_NUMBER: _ClassVar[int]
    ALLOW_NO_INDICES_FIELD_NUMBER: _ClassVar[int]
    ALLOW_PARTIAL_PIT_CREATION_FIELD_NUMBER: _ClassVar[int]
    EXPAND_WILDCARDS_FIELD_NUMBER: _ClassVar[int]
    IGNORE_THROTTLED_FIELD_NUMBER: _ClassVar[int]
    IGNORE_UNAVAILABLE_FIELD_NUMBER: _ClassVar[int]
    PREFERENCE_FIELD_NUMBER: _ClassVar[int]
    ROUTING_FIELD_NUMBER: _ClassVar[int]
    GLOBAL_PARAMS_FIELD_NUMBER: _ClassVar[int]
    index: _containers.RepeatedScalarFieldContainer[str]
    keep_alive: str
    allow_no_indices: bool
    allow_partial_pit_creation: bool
    expand_wildcards: _containers.RepeatedScalarFieldContainer[ExpandWildcard]
    ignore_throttled: bool
    ignore_unavailable: bool
    preference: str
    routing: _containers.RepeatedScalarFieldContainer[str]
    global_params: GlobalParams
    def __init__(self, index: _Optional[_Iterable[str]] = ..., keep_alive: _Optional[str] = ..., allow_no_indices: bool = ..., allow_partial_pit_creation: bool = ..., expand_wildcards: _Optional[_Iterable[_Union[ExpandWildcard, str]]] = ..., ignore_throttled: bool = ..., ignore_unavailable: bool = ..., preference: _Optional[str] = ..., routing: _Optional[_Iterable[str]] = ..., global_params: _Optional[_Union[GlobalParams, _Mapping]] = ...) -> None: ...

class StoredLtrQuery(_message.Message):
    __slots__ = ("active_features", "boost", "cache", "featureset", "model", "params", "store", "x_name")
    ACTIVE_FEATURES_FIELD_NUMBER: _ClassVar[int]
    BOOST_FIELD_NUMBER: _ClassVar[int]
    CACHE_FIELD_NUMBER: _ClassVar[int]
    FEATURESET_FIELD_NUMBER: _ClassVar[int]
    MODEL_FIELD_NUMBER: _ClassVar[int]
    PARAMS_FIELD_NUMBER: _ClassVar[int]
    STORE_FIELD_NUMBER: _ClassVar[int]
    X_NAME_FIELD_NUMBER: _ClassVar[int]
    active_features: _containers.RepeatedScalarFieldContainer[str]
    boost: float
    cache: bool
    featureset: str
    model: str
    params: ObjectMap
    store: str
    x_name: str
    def __init__(self, active_features: _Optional[_Iterable[str]] = ..., boost: _Optional[float] = ..., cache: bool = ..., featureset: _Optional[str] = ..., model: _Optional[str] = ..., params: _Optional[_Union[ObjectMap, _Mapping]] = ..., store: _Optional[str] = ..., x_name: _Optional[str] = ...) -> None: ...

class ObjectMap(_message.Message):
    __slots__ = ("fields",)
    class FieldsEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: ObjectMap.Value
        def __init__(self, key: _Optional[str] = ..., value: _Optional[_Union[ObjectMap.Value, _Mapping]] = ...) -> None: ...
    class Value(_message.Message):
        __slots__ = ("null_value", "int32", "int64", "float", "double", "string", "bool", "object_map", "list_value")
        NULL_VALUE_FIELD_NUMBER: _ClassVar[int]
        INT32_FIELD_NUMBER: _ClassVar[int]
        INT64_FIELD_NUMBER: _ClassVar[int]
        FLOAT_FIELD_NUMBER: _ClassVar[int]
        DOUBLE_FIELD_NUMBER: _ClassVar[int]
        STRING_FIELD_NUMBER: _ClassVar[int]
        BOOL_FIELD_NUMBER: _ClassVar[int]
        OBJECT_MAP_FIELD_NUMBER: _ClassVar[int]
        LIST_VALUE_FIELD_NUMBER: _ClassVar[int]
        null_value: NullValue
        int32: int
        int64: int
        float: float
        double: float
        string: str
        bool: bool
        object_map: ObjectMap
        list_value: ObjectMap.ListValue
        def __init__(self, null_value: _Optional[_Union[NullValue, str]] = ..., int32: _Optional[int] = ..., int64: _Optional[int] = ..., float: _Optional[float] = ..., double: _Optional[float] = ..., string: _Optional[str] = ..., bool: bool = ..., object_map: _Optional[_Union[ObjectMap, _Mapping]] = ..., list_value: _Optional[_Union[ObjectMap.ListValue, _Mapping]] = ...) -> None: ...
    class ListValue(_message.Message):
        __slots__ = ("value",)
        VALUE_FIELD_NUMBER: _ClassVar[int]
        value: _containers.RepeatedCompositeFieldContainer[ObjectMap.Value]
        def __init__(self, value: _Optional[_Iterable[_Union[ObjectMap.Value, _Mapping]]] = ...) -> None: ...
    FIELDS_FIELD_NUMBER: _ClassVar[int]
    fields: _containers.MessageMap[str, ObjectMap.Value]
    def __init__(self, fields: _Optional[_Mapping[str, ObjectMap.Value]] = ...) -> None: ...

class GeneralNumber(_message.Message):
    __slots__ = ("int32_value", "int64_value", "float_value", "double_value", "uint64_value")
    INT32_VALUE_FIELD_NUMBER: _ClassVar[int]
    INT64_VALUE_FIELD_NUMBER: _ClassVar[int]
    FLOAT_VALUE_FIELD_NUMBER: _ClassVar[int]
    DOUBLE_VALUE_FIELD_NUMBER: _ClassVar[int]
    UINT64_VALUE_FIELD_NUMBER: _ClassVar[int]
    int32_value: int
    int64_value: int
    float_value: float
    double_value: float
    uint64_value: int
    def __init__(self, int32_value: _Optional[int] = ..., int64_value: _Optional[int] = ..., float_value: _Optional[float] = ..., double_value: _Optional[float] = ..., uint64_value: _Optional[int] = ...) -> None: ...
