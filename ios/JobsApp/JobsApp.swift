import SwiftUI
import UserNotifications

@main
struct JobsApp: App {
    @UIApplicationDelegateAdaptor(NotificationsDelegate.self) private var notificationDelegate

    var body: some Scene {
        WindowGroup { WorkspaceView() }
    }
}

@MainActor
@Observable
final class Workspace {
    var address = ""
    private(set) var dashboard: Dashboard?
    private(set) var loading = false
    private(set) var saving = false
    private(set) var startingSearch = false
    var connectionError: String?
    var searchError: String?
    private var latestLoad = UUID()
    let isSample: Bool

    init(isSample: Bool = false) {
        self.isSample = isSample
        if isSample { dashboard = SampleWorkspace.restore() }
    }

    func connect(to address: String) {
        self.address = address
        dashboard = nil
        loading = false
        connectionError = nil
        searchError = nil
        latestLoad = UUID()
    }

    func refresh() async {
        guard !isSample, !address.isEmpty else { return }
        let load = UUID()
        latestLoad = load
        loading = true
        defer { if latestLoad == load { loading = false } }
        do {
            let result = try await DashboardAPI.dashboard(at: address)
            guard latestLoad == load, !Task.isCancelled else { return }
            dashboard = result
            connectionError = nil
            await MatchNotifications.deliver(result.matchAlerts ?? [], server: address)
        } catch {
            guard latestLoad == load, !Task.isCancelled else { return }
            connectionError = error is DecodingError
                ? "The server didn’t return a compatible Jobs dashboard." : error.localizedDescription
        }
    }

    func save<T: Encodable>(_ path: String, _ body: T) async throws {
        guard !isSample else {
            throw DashboardAPI.ServerError(status: 0, message: "Connect your Mac to use this feature.")
        }
        guard !saving else {
            throw DashboardAPI.ServerError(status: 409, message: "Another change is being saved.")
        }
        saving = true
        defer { saving = false }
        try await DashboardAPI.post(path, at: address, body: body)
        await refresh()
    }

    func updateInterest(for jobID: Int, to state: String, version: Int) async throws {
        guard isSample else {
            try await save("/api/jobs/\(jobID)/interest", InterestUpdate(state: state, version: version))
            return
        }
        try editSampleJob(jobID) { job in
            guard (job.interest?.version ?? 0) == version else { throw Self.sampleConflict }
            job.interest = Job.Interest(state: state, version: version + 1,
                                        updated: Date.now.ISO8601Format())
        }
    }

    func updateTracking(for jobID: Int, draft: TrackingDraft) async throws {
        guard isSample else {
            try await save("/api/jobs/\(jobID)/tracking", draft)
            return
        }
        try editSampleJob(jobID) { job in
            guard job.version == draft.version else { throw Self.sampleConflict }
            job.status = draft.status
            job.applicationDate = draft.applicationDate
            job.followUp = draft.followUp
            job.notes = draft.notes
            job.version += 1
        }
    }

    private static var sampleConflict: DashboardAPI.ServerError {
        DashboardAPI.ServerError(status: 409, message: "This sample job has changed. Reload to edit it.")
    }

    private func editSampleJob(_ id: Int, change: (inout Job) throws -> Void) throws {
        guard var snapshot = dashboard, let index = snapshot.jobs.firstIndex(where: { $0.id == id })
        else { throw DashboardAPI.ServerError(status: 404, message: "Sample job unavailable.") }
        try change(&snapshot.jobs[index])
        try SampleWorkspace.save(snapshot.jobs)
        dashboard = snapshot
    }

    func resetSample() {
        guard isSample else { return }
        dashboard = SampleWorkspace.reset()
    }

    func startSearch() async {
        guard !startingSearch else { return }
        startingSearch = true
        searchError = nil
        defer { startingSearch = false }
        do {
            try await save("/api/run", [String: String]())
        } catch {
            searchError = error.localizedDescription
            if (error as? DashboardAPI.ServerError)?.status == 409 { await refresh() }
        }
    }
}

private struct WorkspaceView: View {
    @AppStorage("backendURL") private var address = ""
    @State private var workspace = Workspace()
    @State private var editingServer = false

    @State private var sample: Workspace?
    @State private var confirmingSampleReset = false
    @State private var selectedTab: Tab = .forYou

    private enum Tab: Hashable { case forYou, browse, myJobs, search, settings }

    var body: some View {
        Group {
            if let sample {
                tabs(sample)
            } else if workspace.dashboard != nil {
                tabs(workspace)
            } else {
                NavigationStack {
                    WorkspaceWelcome(hasAddress: !address.isEmpty, loading: workspace.loading,
                                     error: workspace.connectionError) {
                        selectedTab = .forYou
                        sample = Workspace(isSample: true)
                    } connect: {
                        editingServer = true
                    } retry: {
                        Task { await workspace.refresh() }
                    }
                }
            }
        }
        .tint(JobsTheme.accent)
        .sheet(isPresented: $editingServer) {
            ServerSettings(address: address) { newAddress in
                selectedTab = .forYou
                sample = nil
                if address == newAddress {
                    Task { await workspace.refresh() }
                } else {
                    address = newAddress
                }
            }
        }
        .task(id: address) {
            workspace.connect(to: address)
            await workspace.refresh()
            while !Task.isCancelled {
                do { try await Task.sleep(for: .seconds(workspace.dashboard?.running == true ? 2 : 10)) }
                catch { break }
                if !workspace.saving && !workspace.loading, workspace.dashboard != nil {
                    await workspace.refresh()
                }
            }
        }
    }

    private func tabs(_ current: Workspace) -> some View {
        TabView(selection: $selectedTab) {
            NavigationStack {
                ForYou(workspace: current, openBrowse: { selectedTab = .browse },
                       openSettings: { selectedTab = .settings })
                    .workspaceNotice(current)
            }
            .tabItem { Label("For You", systemImage: "sparkles") }
            .tag(Tab.forYou)
            NavigationStack { JobList(workspace: current).workspaceNotice(current) }
                .tabItem { Label("Browse", systemImage: "magnifyingglass") }
                .tag(Tab.browse)
            NavigationStack { JobList(workspace: current, trackingOnly: true).workspaceNotice(current) }
                .tabItem { Label("My Jobs", systemImage: "bookmark") }
                .tag(Tab.myJobs)
            if !current.isSample {
                NavigationStack { SearchScreen(workspace: current).workspaceNotice(current) }
                    .tabItem { Label("Alerts", systemImage: "bell") }
                    .tag(Tab.search)
                    .badge(current.dashboard?.unreadMatchCount ?? 0)
            }
            NavigationStack {
                if current.isSample {
                    List {
                        Section("Sample Workspace") {
                            Text("These listings are fictional. Your sample progress stays on this iPhone.")
                            Button("Connect to your Mac", systemImage: "desktopcomputer") { editingServer = true }
                            Button("Reset Sample Progress", role: .destructive) {
                                confirmingSampleReset = true
                            }
                            Button("Leave Sample Workspace") {
                                selectedTab = .forYou
                                sample = nil
                            }
                        }
                    }
                    .navigationTitle("Settings")
                    .confirmationDialog("Reset sample progress?", isPresented: $confirmingSampleReset,
                                        titleVisibility: .visible) {
                        Button("Reset Sample Progress", role: .destructive) {
                            current.resetSample()
                            // Recreate the sample tabs so stale Undo actions cannot affect a new session.
                            sample = nil
                            selectedTab = .forYou
                        }
                    } message: {
                        Text("This clears sample saves, passes, notes and application dates.")
                    }
                } else {
                    PreferencesScreen(workspace: current) { editingServer = true }
                        .workspaceNotice(current)
                }
            }
            .tabItem { Label("Settings", systemImage: "gearshape") }
            .tag(Tab.settings)
        }
        .id(current.isSample ? "sample" : current.address)
    }
}

extension View {
    @MainActor
    func workspaceNotice(_ current: Workspace) -> some View {
        safeAreaInset(edge: .top, spacing: 0) {
            if current.isSample {
                Label("Sample workspace · Fictional listings", systemImage: "eye")
                    .font(.footnote.weight(.semibold))
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 8)
                    .background(.regularMaterial)
            } else if let message = current.connectionError {
                Button {
                    Task { await current.refresh() }
                } label: {
                    Label("Connection lost. Tap to retry.", systemImage: "wifi.exclamationmark")
                        .frame(maxWidth: .infinity)
                        .padding(8)
                }
                .accessibilityHint(message)
                .background(.regularMaterial)
            }
        }
    }
}

private struct ServerSettings: View {
    @Environment(\.dismiss) private var dismiss
    @State var address: String
    let save: (String) -> Void

    var body: some View {
        NavigationStack {
            Form {
                Section("Mac workspace address") {
                    TextField("http://your-mac.local:8084", text: $address)
                        .keyboardType(.URL)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                    Text("For a simulator on your Mac, use http://localhost:8084.")
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                }
            }
            .navigationTitle("Server Settings")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { dismiss() }
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Save") {
                        save(address.trimmingCharacters(in: .whitespacesAndNewlines))
                        dismiss()
                    }
                    .disabled(DashboardAPI.endpoint("/api/v1/dashboard", at: address) == nil)
                }
            }
        }
    }
}
