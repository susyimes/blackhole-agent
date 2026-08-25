# Generated from PartiQLParser.g4 by ANTLR 4.13.2
from antlr4 import *
if "." in __name__:
    from .PartiQLParser import PartiQLParser
else:
    from PartiQLParser import PartiQLParser

# This class defines a complete generic visitor for a parse tree produced by PartiQLParser.

class PartiQLParserVisitor(ParseTreeVisitor):

    # Visit a parse tree produced by PartiQLParser#root.
    def visitRoot(self, ctx:PartiQLParser.RootContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#QueryDql.
    def visitQueryDql(self, ctx:PartiQLParser.QueryDqlContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#QueryDml.
    def visitQueryDml(self, ctx:PartiQLParser.QueryDmlContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#QueryDdl.
    def visitQueryDdl(self, ctx:PartiQLParser.QueryDdlContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#QueryExec.
    def visitQueryExec(self, ctx:PartiQLParser.QueryExecContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#explainOption.
    def visitExplainOption(self, ctx:PartiQLParser.ExplainOptionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#asIdent.
    def visitAsIdent(self, ctx:PartiQLParser.AsIdentContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#atIdent.
    def visitAtIdent(self, ctx:PartiQLParser.AtIdentContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#byIdent.
    def visitByIdent(self, ctx:PartiQLParser.ByIdentContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#symbolPrimitive.
    def visitSymbolPrimitive(self, ctx:PartiQLParser.SymbolPrimitiveContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#dql.
    def visitDql(self, ctx:PartiQLParser.DqlContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#execCommand.
    def visitExecCommand(self, ctx:PartiQLParser.ExecCommandContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#qualifiedName.
    def visitQualifiedName(self, ctx:PartiQLParser.QualifiedNameContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#tableName.
    def visitTableName(self, ctx:PartiQLParser.TableNameContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#tableConstraintName.
    def visitTableConstraintName(self, ctx:PartiQLParser.TableConstraintNameContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#columnName.
    def visitColumnName(self, ctx:PartiQLParser.ColumnNameContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#columnConstraintName.
    def visitColumnConstraintName(self, ctx:PartiQLParser.ColumnConstraintNameContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#ddl.
    def visitDdl(self, ctx:PartiQLParser.DdlContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#CreateTable.
    def visitCreateTable(self, ctx:PartiQLParser.CreateTableContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#CreateIndex.
    def visitCreateIndex(self, ctx:PartiQLParser.CreateIndexContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#CreateView.
    def visitCreateView(self, ctx:PartiQLParser.CreateViewContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#DropTable.
    def visitDropTable(self, ctx:PartiQLParser.DropTableContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#DropIndex.
    def visitDropIndex(self, ctx:PartiQLParser.DropIndexContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#DropView.
    def visitDropView(self, ctx:PartiQLParser.DropViewContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#tableDef.
    def visitTableDef(self, ctx:PartiQLParser.TableDefContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#ColumnDeclaration.
    def visitColumnDeclaration(self, ctx:PartiQLParser.ColumnDeclarationContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#columnConstraint.
    def visitColumnConstraint(self, ctx:PartiQLParser.ColumnConstraintContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#ColConstrNotNull.
    def visitColConstrNotNull(self, ctx:PartiQLParser.ColConstrNotNullContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#ColConstrNull.
    def visitColConstrNull(self, ctx:PartiQLParser.ColConstrNullContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#DmlBaseWrapper.
    def visitDmlBaseWrapper(self, ctx:PartiQLParser.DmlBaseWrapperContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#DmlDelete.
    def visitDmlDelete(self, ctx:PartiQLParser.DmlDeleteContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#DmlInsertReturning.
    def visitDmlInsertReturning(self, ctx:PartiQLParser.DmlInsertReturningContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#DmlBase.
    def visitDmlBase(self, ctx:PartiQLParser.DmlBaseContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#dmlBaseCommand.
    def visitDmlBaseCommand(self, ctx:PartiQLParser.DmlBaseCommandContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#pathSimple.
    def visitPathSimple(self, ctx:PartiQLParser.PathSimpleContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#PathSimpleLiteral.
    def visitPathSimpleLiteral(self, ctx:PartiQLParser.PathSimpleLiteralContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#PathSimpleSymbol.
    def visitPathSimpleSymbol(self, ctx:PartiQLParser.PathSimpleSymbolContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#PathSimpleDotSymbol.
    def visitPathSimpleDotSymbol(self, ctx:PartiQLParser.PathSimpleDotSymbolContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#replaceCommand.
    def visitReplaceCommand(self, ctx:PartiQLParser.ReplaceCommandContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#upsertCommand.
    def visitUpsertCommand(self, ctx:PartiQLParser.UpsertCommandContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#removeCommand.
    def visitRemoveCommand(self, ctx:PartiQLParser.RemoveCommandContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#insertCommandReturning.
    def visitInsertCommandReturning(self, ctx:PartiQLParser.InsertCommandReturningContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#insertStatement.
    def visitInsertStatement(self, ctx:PartiQLParser.InsertStatementContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#columnList.
    def visitColumnList(self, ctx:PartiQLParser.ColumnListContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#onConflict.
    def visitOnConflict(self, ctx:PartiQLParser.OnConflictContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#insertStatementLegacy.
    def visitInsertStatementLegacy(self, ctx:PartiQLParser.InsertStatementLegacyContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#onConflictLegacy.
    def visitOnConflictLegacy(self, ctx:PartiQLParser.OnConflictLegacyContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#conflictTarget.
    def visitConflictTarget(self, ctx:PartiQLParser.ConflictTargetContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#constraintName.
    def visitConstraintName(self, ctx:PartiQLParser.ConstraintNameContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#conflictAction.
    def visitConflictAction(self, ctx:PartiQLParser.ConflictActionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#doReplace.
    def visitDoReplace(self, ctx:PartiQLParser.DoReplaceContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#doUpdate.
    def visitDoUpdate(self, ctx:PartiQLParser.DoUpdateContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#updateClause.
    def visitUpdateClause(self, ctx:PartiQLParser.UpdateClauseContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#setCommand.
    def visitSetCommand(self, ctx:PartiQLParser.SetCommandContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#setAssignment.
    def visitSetAssignment(self, ctx:PartiQLParser.SetAssignmentContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#deleteCommand.
    def visitDeleteCommand(self, ctx:PartiQLParser.DeleteCommandContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#returningClause.
    def visitReturningClause(self, ctx:PartiQLParser.ReturningClauseContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#returningColumn.
    def visitReturningColumn(self, ctx:PartiQLParser.ReturningColumnContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#FromClauseSimpleExplicit.
    def visitFromClauseSimpleExplicit(self, ctx:PartiQLParser.FromClauseSimpleExplicitContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#FromClauseSimpleImplicit.
    def visitFromClauseSimpleImplicit(self, ctx:PartiQLParser.FromClauseSimpleImplicitContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#whereClause.
    def visitWhereClause(self, ctx:PartiQLParser.WhereClauseContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#SelectAll.
    def visitSelectAll(self, ctx:PartiQLParser.SelectAllContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#SelectItems.
    def visitSelectItems(self, ctx:PartiQLParser.SelectItemsContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#SelectValue.
    def visitSelectValue(self, ctx:PartiQLParser.SelectValueContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#SelectPivot.
    def visitSelectPivot(self, ctx:PartiQLParser.SelectPivotContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#projectionItems.
    def visitProjectionItems(self, ctx:PartiQLParser.ProjectionItemsContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#projectionItem.
    def visitProjectionItem(self, ctx:PartiQLParser.ProjectionItemContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#setQuantifierStrategy.
    def visitSetQuantifierStrategy(self, ctx:PartiQLParser.SetQuantifierStrategyContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#letClause.
    def visitLetClause(self, ctx:PartiQLParser.LetClauseContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#letBinding.
    def visitLetBinding(self, ctx:PartiQLParser.LetBindingContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#orderByClause.
    def visitOrderByClause(self, ctx:PartiQLParser.OrderByClauseContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#orderSortSpec.
    def visitOrderSortSpec(self, ctx:PartiQLParser.OrderSortSpecContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#groupClause.
    def visitGroupClause(self, ctx:PartiQLParser.GroupClauseContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#groupAlias.
    def visitGroupAlias(self, ctx:PartiQLParser.GroupAliasContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#groupKey.
    def visitGroupKey(self, ctx:PartiQLParser.GroupKeyContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#over.
    def visitOver(self, ctx:PartiQLParser.OverContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#windowPartitionList.
    def visitWindowPartitionList(self, ctx:PartiQLParser.WindowPartitionListContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#windowSortSpecList.
    def visitWindowSortSpecList(self, ctx:PartiQLParser.WindowSortSpecListContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#havingClause.
    def visitHavingClause(self, ctx:PartiQLParser.HavingClauseContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#excludeClause.
    def visitExcludeClause(self, ctx:PartiQLParser.ExcludeClauseContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#excludeExpr.
    def visitExcludeExpr(self, ctx:PartiQLParser.ExcludeExprContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#ExcludeExprTupleAttr.
    def visitExcludeExprTupleAttr(self, ctx:PartiQLParser.ExcludeExprTupleAttrContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#ExcludeExprCollectionAttr.
    def visitExcludeExprCollectionAttr(self, ctx:PartiQLParser.ExcludeExprCollectionAttrContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#ExcludeExprCollectionIndex.
    def visitExcludeExprCollectionIndex(self, ctx:PartiQLParser.ExcludeExprCollectionIndexContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#ExcludeExprCollectionWildcard.
    def visitExcludeExprCollectionWildcard(self, ctx:PartiQLParser.ExcludeExprCollectionWildcardContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#ExcludeExprTupleWildcard.
    def visitExcludeExprTupleWildcard(self, ctx:PartiQLParser.ExcludeExprTupleWildcardContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#fromClause.
    def visitFromClause(self, ctx:PartiQLParser.FromClauseContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#whereClauseSelect.
    def visitWhereClauseSelect(self, ctx:PartiQLParser.WhereClauseSelectContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#offsetByClause.
    def visitOffsetByClause(self, ctx:PartiQLParser.OffsetByClauseContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#limitClause.
    def visitLimitClause(self, ctx:PartiQLParser.LimitClauseContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#gpmlPattern.
    def visitGpmlPattern(self, ctx:PartiQLParser.GpmlPatternContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#gpmlPatternList.
    def visitGpmlPatternList(self, ctx:PartiQLParser.GpmlPatternListContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#matchPattern.
    def visitMatchPattern(self, ctx:PartiQLParser.MatchPatternContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#graphPart.
    def visitGraphPart(self, ctx:PartiQLParser.GraphPartContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#SelectorBasic.
    def visitSelectorBasic(self, ctx:PartiQLParser.SelectorBasicContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#SelectorAny.
    def visitSelectorAny(self, ctx:PartiQLParser.SelectorAnyContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#SelectorShortest.
    def visitSelectorShortest(self, ctx:PartiQLParser.SelectorShortestContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#patternPathVariable.
    def visitPatternPathVariable(self, ctx:PartiQLParser.PatternPathVariableContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#patternRestrictor.
    def visitPatternRestrictor(self, ctx:PartiQLParser.PatternRestrictorContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#node.
    def visitNode(self, ctx:PartiQLParser.NodeContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#EdgeWithSpec.
    def visitEdgeWithSpec(self, ctx:PartiQLParser.EdgeWithSpecContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#EdgeAbbreviated.
    def visitEdgeAbbreviated(self, ctx:PartiQLParser.EdgeAbbreviatedContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#pattern.
    def visitPattern(self, ctx:PartiQLParser.PatternContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#patternQuantifier.
    def visitPatternQuantifier(self, ctx:PartiQLParser.PatternQuantifierContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#EdgeSpecRight.
    def visitEdgeSpecRight(self, ctx:PartiQLParser.EdgeSpecRightContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#EdgeSpecUndirected.
    def visitEdgeSpecUndirected(self, ctx:PartiQLParser.EdgeSpecUndirectedContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#EdgeSpecLeft.
    def visitEdgeSpecLeft(self, ctx:PartiQLParser.EdgeSpecLeftContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#EdgeSpecUndirectedRight.
    def visitEdgeSpecUndirectedRight(self, ctx:PartiQLParser.EdgeSpecUndirectedRightContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#EdgeSpecUndirectedLeft.
    def visitEdgeSpecUndirectedLeft(self, ctx:PartiQLParser.EdgeSpecUndirectedLeftContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#EdgeSpecBidirectional.
    def visitEdgeSpecBidirectional(self, ctx:PartiQLParser.EdgeSpecBidirectionalContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#EdgeSpecUndirectedBidirectional.
    def visitEdgeSpecUndirectedBidirectional(self, ctx:PartiQLParser.EdgeSpecUndirectedBidirectionalContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#edgeSpec.
    def visitEdgeSpec(self, ctx:PartiQLParser.EdgeSpecContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#LabelSpecTerm.
    def visitLabelSpecTerm(self, ctx:PartiQLParser.LabelSpecTermContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#LabelSpecOr.
    def visitLabelSpecOr(self, ctx:PartiQLParser.LabelSpecOrContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#LabelTermFactor.
    def visitLabelTermFactor(self, ctx:PartiQLParser.LabelTermFactorContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#LabelTermAnd.
    def visitLabelTermAnd(self, ctx:PartiQLParser.LabelTermAndContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#LabelFactorNot.
    def visitLabelFactorNot(self, ctx:PartiQLParser.LabelFactorNotContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#LabelFactorPrimary.
    def visitLabelFactorPrimary(self, ctx:PartiQLParser.LabelFactorPrimaryContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#LabelPrimaryName.
    def visitLabelPrimaryName(self, ctx:PartiQLParser.LabelPrimaryNameContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#LabelPrimaryWild.
    def visitLabelPrimaryWild(self, ctx:PartiQLParser.LabelPrimaryWildContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#LabelPrimaryParen.
    def visitLabelPrimaryParen(self, ctx:PartiQLParser.LabelPrimaryParenContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#edgeAbbrev.
    def visitEdgeAbbrev(self, ctx:PartiQLParser.EdgeAbbrevContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#TableWrapped.
    def visitTableWrapped(self, ctx:PartiQLParser.TableWrappedContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#TableCrossJoin.
    def visitTableCrossJoin(self, ctx:PartiQLParser.TableCrossJoinContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#TableQualifiedJoin.
    def visitTableQualifiedJoin(self, ctx:PartiQLParser.TableQualifiedJoinContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#TableRefBase.
    def visitTableRefBase(self, ctx:PartiQLParser.TableRefBaseContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#tableNonJoin.
    def visitTableNonJoin(self, ctx:PartiQLParser.TableNonJoinContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#TableBaseRefSymbol.
    def visitTableBaseRefSymbol(self, ctx:PartiQLParser.TableBaseRefSymbolContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#TableBaseRefClauses.
    def visitTableBaseRefClauses(self, ctx:PartiQLParser.TableBaseRefClausesContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#TableBaseRefMatch.
    def visitTableBaseRefMatch(self, ctx:PartiQLParser.TableBaseRefMatchContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#tableUnpivot.
    def visitTableUnpivot(self, ctx:PartiQLParser.TableUnpivotContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#JoinRhsBase.
    def visitJoinRhsBase(self, ctx:PartiQLParser.JoinRhsBaseContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#JoinRhsTableJoined.
    def visitJoinRhsTableJoined(self, ctx:PartiQLParser.JoinRhsTableJoinedContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#joinSpec.
    def visitJoinSpec(self, ctx:PartiQLParser.JoinSpecContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#joinType.
    def visitJoinType(self, ctx:PartiQLParser.JoinTypeContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#expr.
    def visitExpr(self, ctx:PartiQLParser.ExprContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#Intersect.
    def visitIntersect(self, ctx:PartiQLParser.IntersectContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#QueryBase.
    def visitQueryBase(self, ctx:PartiQLParser.QueryBaseContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#Except.
    def visitExcept(self, ctx:PartiQLParser.ExceptContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#Union.
    def visitUnion(self, ctx:PartiQLParser.UnionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#SfwQuery.
    def visitSfwQuery(self, ctx:PartiQLParser.SfwQueryContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#SfwBase.
    def visitSfwBase(self, ctx:PartiQLParser.SfwBaseContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#Or.
    def visitOr(self, ctx:PartiQLParser.OrContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#ExprOrBase.
    def visitExprOrBase(self, ctx:PartiQLParser.ExprOrBaseContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#ExprAndBase.
    def visitExprAndBase(self, ctx:PartiQLParser.ExprAndBaseContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#And.
    def visitAnd(self, ctx:PartiQLParser.AndContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#Not.
    def visitNot(self, ctx:PartiQLParser.NotContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#ExprNotBase.
    def visitExprNotBase(self, ctx:PartiQLParser.ExprNotBaseContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#PredicateIn.
    def visitPredicateIn(self, ctx:PartiQLParser.PredicateInContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#PredicateBetween.
    def visitPredicateBetween(self, ctx:PartiQLParser.PredicateBetweenContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#PredicateBase.
    def visitPredicateBase(self, ctx:PartiQLParser.PredicateBaseContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#PredicateComparison.
    def visitPredicateComparison(self, ctx:PartiQLParser.PredicateComparisonContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#PredicateIs.
    def visitPredicateIs(self, ctx:PartiQLParser.PredicateIsContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#PredicateLike.
    def visitPredicateLike(self, ctx:PartiQLParser.PredicateLikeContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#mathOp00.
    def visitMathOp00(self, ctx:PartiQLParser.MathOp00Context):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#mathOp01.
    def visitMathOp01(self, ctx:PartiQLParser.MathOp01Context):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#mathOp02.
    def visitMathOp02(self, ctx:PartiQLParser.MathOp02Context):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#valueExpr.
    def visitValueExpr(self, ctx:PartiQLParser.ValueExprContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#ExprPrimaryPath.
    def visitExprPrimaryPath(self, ctx:PartiQLParser.ExprPrimaryPathContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#ExprPrimaryBase.
    def visitExprPrimaryBase(self, ctx:PartiQLParser.ExprPrimaryBaseContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#ExprTermWrappedQuery.
    def visitExprTermWrappedQuery(self, ctx:PartiQLParser.ExprTermWrappedQueryContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#ExprTermCurrentUser.
    def visitExprTermCurrentUser(self, ctx:PartiQLParser.ExprTermCurrentUserContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#ExprTermCurrentDate.
    def visitExprTermCurrentDate(self, ctx:PartiQLParser.ExprTermCurrentDateContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#ExprTermBase.
    def visitExprTermBase(self, ctx:PartiQLParser.ExprTermBaseContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#nullIf.
    def visitNullIf(self, ctx:PartiQLParser.NullIfContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#coalesce.
    def visitCoalesce(self, ctx:PartiQLParser.CoalesceContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#caseExpr.
    def visitCaseExpr(self, ctx:PartiQLParser.CaseExprContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#values.
    def visitValues(self, ctx:PartiQLParser.ValuesContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#valueRow.
    def visitValueRow(self, ctx:PartiQLParser.ValueRowContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#valueList.
    def visitValueList(self, ctx:PartiQLParser.ValueListContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#sequenceConstructor.
    def visitSequenceConstructor(self, ctx:PartiQLParser.SequenceConstructorContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#substring.
    def visitSubstring(self, ctx:PartiQLParser.SubstringContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#position.
    def visitPosition(self, ctx:PartiQLParser.PositionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#overlay.
    def visitOverlay(self, ctx:PartiQLParser.OverlayContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#CountAll.
    def visitCountAll(self, ctx:PartiQLParser.CountAllContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#AggregateBase.
    def visitAggregateBase(self, ctx:PartiQLParser.AggregateBaseContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#LagLeadFunction.
    def visitLagLeadFunction(self, ctx:PartiQLParser.LagLeadFunctionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#cast.
    def visitCast(self, ctx:PartiQLParser.CastContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#canLosslessCast.
    def visitCanLosslessCast(self, ctx:PartiQLParser.CanLosslessCastContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#canCast.
    def visitCanCast(self, ctx:PartiQLParser.CanCastContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#extract.
    def visitExtract(self, ctx:PartiQLParser.ExtractContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#trimFunction.
    def visitTrimFunction(self, ctx:PartiQLParser.TrimFunctionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#dateFunction.
    def visitDateFunction(self, ctx:PartiQLParser.DateFunctionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#functionCall.
    def visitFunctionCall(self, ctx:PartiQLParser.FunctionCallContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#FunctionNameReserved.
    def visitFunctionNameReserved(self, ctx:PartiQLParser.FunctionNameReservedContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#FunctionNameSymbol.
    def visitFunctionNameSymbol(self, ctx:PartiQLParser.FunctionNameSymbolContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#PathStepIndexExpr.
    def visitPathStepIndexExpr(self, ctx:PartiQLParser.PathStepIndexExprContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#PathStepIndexAll.
    def visitPathStepIndexAll(self, ctx:PartiQLParser.PathStepIndexAllContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#PathStepDotExpr.
    def visitPathStepDotExpr(self, ctx:PartiQLParser.PathStepDotExprContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#PathStepDotAll.
    def visitPathStepDotAll(self, ctx:PartiQLParser.PathStepDotAllContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#exprGraphMatchMany.
    def visitExprGraphMatchMany(self, ctx:PartiQLParser.ExprGraphMatchManyContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#exprGraphMatchOne.
    def visitExprGraphMatchOne(self, ctx:PartiQLParser.ExprGraphMatchOneContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#parameter.
    def visitParameter(self, ctx:PartiQLParser.ParameterContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#VariableIdentifier.
    def visitVariableIdentifier(self, ctx:PartiQLParser.VariableIdentifierContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#VariableKeyword.
    def visitVariableKeyword(self, ctx:PartiQLParser.VariableKeywordContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#nonReservedKeywords.
    def visitNonReservedKeywords(self, ctx:PartiQLParser.NonReservedKeywordsContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#collection.
    def visitCollection(self, ctx:PartiQLParser.CollectionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#array.
    def visitArray(self, ctx:PartiQLParser.ArrayContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#bag.
    def visitBag(self, ctx:PartiQLParser.BagContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#tuple.
    def visitTuple(self, ctx:PartiQLParser.TupleContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#pair.
    def visitPair(self, ctx:PartiQLParser.PairContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#LiteralNull.
    def visitLiteralNull(self, ctx:PartiQLParser.LiteralNullContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#LiteralMissing.
    def visitLiteralMissing(self, ctx:PartiQLParser.LiteralMissingContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#LiteralTrue.
    def visitLiteralTrue(self, ctx:PartiQLParser.LiteralTrueContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#LiteralFalse.
    def visitLiteralFalse(self, ctx:PartiQLParser.LiteralFalseContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#LiteralString.
    def visitLiteralString(self, ctx:PartiQLParser.LiteralStringContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#LiteralInteger.
    def visitLiteralInteger(self, ctx:PartiQLParser.LiteralIntegerContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#LiteralDecimal.
    def visitLiteralDecimal(self, ctx:PartiQLParser.LiteralDecimalContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#LiteralIon.
    def visitLiteralIon(self, ctx:PartiQLParser.LiteralIonContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#LiteralDate.
    def visitLiteralDate(self, ctx:PartiQLParser.LiteralDateContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#LiteralTime.
    def visitLiteralTime(self, ctx:PartiQLParser.LiteralTimeContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#LiteralTimestamp.
    def visitLiteralTimestamp(self, ctx:PartiQLParser.LiteralTimestampContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#TypeAtomic.
    def visitTypeAtomic(self, ctx:PartiQLParser.TypeAtomicContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#TypeArgSingle.
    def visitTypeArgSingle(self, ctx:PartiQLParser.TypeArgSingleContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#TypeVarChar.
    def visitTypeVarChar(self, ctx:PartiQLParser.TypeVarCharContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#TypeArgDouble.
    def visitTypeArgDouble(self, ctx:PartiQLParser.TypeArgDoubleContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#TypeTimeZone.
    def visitTypeTimeZone(self, ctx:PartiQLParser.TypeTimeZoneContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PartiQLParser#TypeCustom.
    def visitTypeCustom(self, ctx:PartiQLParser.TypeCustomContext):
        return self.visitChildren(ctx)



del PartiQLParser