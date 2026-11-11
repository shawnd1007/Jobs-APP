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

    func connect(to address: String) {
        self.address = address
        dashboard = nil
        loading = false
        connectionError = nil
        searchError = nil
        latestLoad = UUID()
    }

    func refresh() async {
        guard !address.isEmpty else { return }
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
        guard !saving else {
            throw DashboardAPI.ServerError(status: 409, message: "Another change is being saved.")
        }
        saving = true
        defer { saving = false }
        try await DashboardAPI.post(path, at: address, body: body)
        await refresh()
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

    var body: some View {
        Group {
            if workspace.dashboard != nil {
                TabView {
                    NavigationStack { ForYou(workspace: workspace) }
                        .tabItem { Label("For You", systemImage: "sparkles") }
                    NavigationStack { JobList(workspace: workspace) }
                        .tabItem { Label("Browse", systemImage: "list.bullet") }
                    NavigationStack { SearchScreen(workspace: workspace) }
                        .tabItem { Label("Search", systemImage: "magnifyingglass") }
                        .badge(workspace.dashboard?.unreadMatchCount ?? 0)
                    NavigationStack { JobList(workspace: workspace, trackingOnly: true) }
                        .tabItem { Label("My Jobs", systemImage: "bookmark") }
                    NavigationStack {
                        PreferencesScreen(workspace: workspace) { editingServer = true }
                    }
                    .tabItem { Label("Settings", systemImage: "gearshape") }
                }
                .id(workspace.address)
                .safeAreaInset(edge: .top) {
                    if let message = workspace.connectionError {
                        Button {
                            Task { await workspace.refresh() }
                        } label: {
                            Label("Refresh failed. Tap to retry.", systemImage: "wifi.exclamationmark")
                        }
                        .accessibilityHint(message)
                        .padding(8)
                        .frame(maxWidth: .infinity)
                        .background(.regularMaterial)
                    }
                }
            } else {
                NavigationStack {
                    Group {
                        if workspace.loading {
                            ProgressView("Loading workspace…")
                        } else {
                            ContentUnavailableView {
                                Label(address.isEmpty ? "Connect to Jobs" : "Couldn’t Load Jobs",
                                      systemImage: address.isEmpty ? "desktopcomputer" : "wifi.exclamationmark")
                            } description: {
                                Text(workspace.connectionError ?? "Enter the address of the Jobs server running on your Mac.")
                            } actions: {
                                Button("Set Server Address") { editingServer = true }
                                if !address.isEmpty {
                                    Button("Try Again") { Task { await workspace.refresh() } }
                                }
                            }
                        }
                    }
                    .navigationTitle("Jobs")
                }
            }
        }
        .tint(Color(red: 0.03, green: 0.49, blue: 0.52))
        .sheet(isPresented: $editingServer) {
            ServerSettings(address: address) { newAddress in
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
}

private struct ServerSettings: View {
    @Environment(\.dismiss) private var dismiss
    @State var address: String
    let save: (String) -> Void

    var body: some View {
        NavigationStack {
            Form {
                Section("Backend URL") {
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
