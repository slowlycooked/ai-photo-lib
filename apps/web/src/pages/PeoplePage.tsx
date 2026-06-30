import { Navigate } from "react-router-dom";
import { PeopleHeader } from "@/components/people/PeopleHeader";
import { PeopleSidebar } from "@/components/people/PeopleSidebar";
import { PeopleToolbar } from "@/components/people/PeopleToolbar";
import { PersonDetailPanel } from "@/components/people/PersonDetailPanel";
import { usePeoplePage } from "@/hooks/usePeoplePage";

export function PeoplePage() {
  const {
    currentProject,
    selectedProjectId,
    normalizedRouteProjectId,
    faceCropEnabled,
    statusMessage,
    errorMessage,
    createDisplayName,
    setCreateDisplayName,
    filterMode,
    setFilterMode,
    searchText,
    setSearchText,
    people,
    archivedPeople,
    peopleLoading,
    peopleError,
    resolvedSelectedPersonId,
    selectedPersonIsArchived,
    selectedPersonIsManageable,
    personDetail,
    personLoading,
    personFetching,
    personError,
    actionBusy,
    moveCandidates,
    reviewFaceIds,
    namedCount,
    unnamedCount,
    mergeTargetId,
    manualArchivedPersonIds,
    selectedPersonIds,
    setSelectedPersonId,
    setMergeTargetId,
    toggleSelectPerson,
    archivePerson,
    archiveSelectedPerson,
    archiveSelectedPeople,
    unarchivePerson,
    loadedAssignmentCount,
    totalAssignmentCount,
    canLoadMoreAssignments,
    loadMoreAssignments,
    createPerson,
    mergeSelectedPerson,
    deletePerson,
    deleteSelectedPerson,
    renameSelectedPerson,
    confirmFace,
    rejectFace,
    moveFace,
    batchConfirmReview,
    batchRejectReview,
    batchMoveReview,
    splitFaces,
    setRepresentativeFace,
    rematchSelectedPerson,
    personRematchRunning,
  } = usePeoplePage();

  if (selectedProjectId == null) {
    return (
      <main className="max-w-[1440px] mx-auto px-4 sm:px-6 py-6">
        <div className="bg-canvas border border-hairline rounded-xl p-6 text-mute">
          请先选择一个项目，再查看人物页。
        </div>
      </main>
    );
  }

  if (normalizedRouteProjectId == null) {
    return <Navigate to={`/projects/${selectedProjectId}/people`} replace />;
  }

  return (
    <main className="max-w-[1440px] mx-auto px-4 sm:px-6 py-6 space-y-6">
      <PeopleHeader
        projectId={selectedProjectId}
        projectName={
          currentProject?.id === selectedProjectId ? currentProject.name : `#${selectedProjectId}`
        }
        peopleCount={people.length}
        namedCount={namedCount}
        unnamedCount={unnamedCount}
      />

      <PeopleToolbar
        filterMode={filterMode}
        setFilterMode={setFilterMode}
        searchText={searchText}
        setSearchText={setSearchText}
        createDisplayName={createDisplayName}
        setCreateDisplayName={setCreateDisplayName}
        actionBusy={actionBusy}
        onCreatePerson={createPerson}
        hasSelectedPerson={selectedPersonIsManageable}
        selectedPersonCount={selectedPersonIds.length}
        moveCandidates={moveCandidates}
        mergeTargetId={mergeTargetId}
        setMergeTargetId={setMergeTargetId}
        onMergeSelectedPerson={mergeSelectedPerson}
        onArchiveSelectedPerson={archiveSelectedPerson}
        onArchiveSelectedPeople={archiveSelectedPeople}
        onDeleteSelectedPerson={() => {
          if (!window.confirm("删除人物前，请确保没有 active assignment。确认继续？")) return;
          deleteSelectedPerson();
        }}
      />

      <div className="grid grid-cols-1 gap-5 lg:h-[calc(100vh-260px)] lg:min-h-[560px] lg:grid-cols-[360px_minmax(0,1fr)] lg:overflow-hidden">
        <PeopleSidebar
          projectId={selectedProjectId}
          faceCropEnabled={faceCropEnabled}
          people={people}
          archivedPeople={archivedPeople}
          manualArchivedPersonIds={manualArchivedPersonIds}
          selectedPersonIds={selectedPersonIds}
          peopleLoading={peopleLoading}
          peopleError={peopleError as Error | null}
          selectedPersonId={resolvedSelectedPersonId}
          actionBusy={actionBusy}
          onSelectPerson={setSelectedPersonId}
          onToggleSelectPerson={toggleSelectPerson}
          onArchivePerson={archivePerson}
          onDeletePerson={deletePerson}
          onUnarchivePerson={unarchivePerson}
        />

        <section className="min-h-0 lg:overflow-y-auto lg:overscroll-contain lg:pr-1">
          <PersonDetailPanel
            projectId={selectedProjectId}
            faceCropEnabled={faceCropEnabled}
            detail={personDetail}
            isLoading={personLoading}
            isFetching={personFetching}
            error={personError as Error | null}
            moveCandidates={moveCandidates}
            reviewFaceIds={reviewFaceIds}
            statusMessage={statusMessage}
            errorMessage={errorMessage}
            actionBusy={actionBusy || selectedPersonIsArchived}
            loadedAssignmentCount={loadedAssignmentCount}
            totalAssignmentCount={totalAssignmentCount}
            canLoadMoreAssignments={canLoadMoreAssignments}
            onLoadMoreAssignments={loadMoreAssignments}
            rematchBusy={personRematchRunning}
            onRematchPersonFaces={() => {
              if (!resolvedSelectedPersonId || !selectedPersonIsManageable) return;
              rematchSelectedPerson();
            }}
            onRename={(displayName) => {
              if (!resolvedSelectedPersonId || !selectedPersonIsManageable) return;
              renameSelectedPerson(displayName);
            }}
            onConfirmFace={(faceId) => {
              if (!resolvedSelectedPersonId || !selectedPersonIsManageable) return;
              confirmFace(faceId);
            }}
            onRejectFace={(faceId) => {
              if (!resolvedSelectedPersonId || !selectedPersonIsManageable) return;
              rejectFace(faceId);
            }}
            onMoveFace={(faceId, targetPersonId) => {
              if (!resolvedSelectedPersonId || !selectedPersonIsManageable) return;
              moveFace(faceId, targetPersonId);
            }}
            onBatchConfirmReview={(faceIds) => {
              if (!resolvedSelectedPersonId || !selectedPersonIsManageable || faceIds.length === 0) return;
              batchConfirmReview(faceIds);
            }}
            onBatchRejectReview={(faceIds) => {
              if (!resolvedSelectedPersonId || !selectedPersonIsManageable || faceIds.length === 0) return;
              batchRejectReview(faceIds);
            }}
            onBatchMoveReview={(faceIds, targetPersonId) => {
              if (!resolvedSelectedPersonId || !selectedPersonIsManageable || faceIds.length === 0) return;
              batchMoveReview(faceIds, targetPersonId);
            }}
            onSplitFaces={(faceIds, newDisplayName) => {
              if (!resolvedSelectedPersonId || !selectedPersonIsManageable || faceIds.length === 0) return;
              splitFaces(faceIds, newDisplayName);
            }}
            onSetRepresentative={(faceId) => {
              if (!resolvedSelectedPersonId || !selectedPersonIsManageable) return;
              setRepresentativeFace(faceId);
            }}
          />
        </section>
      </div>
    </main>
  );
}
