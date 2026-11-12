import SwiftUI

struct SaveForm<Content: View>: View {
    @Environment(\.dismiss) private var dismiss
    let title: String
    let workspace: Workspace
    @ViewBuilder let content: () -> Content
    let save: () async throws -> Void
    let reload: () -> Void
    @State private var errorMessage: String?
    @State private var hasConflict = false
    @State private var refreshing = false
    @State private var confirmingReload = false

    var body: some View {
        NavigationStack {
            Form {
                if !workspace.canWrite {
                    Section {
                        Label("Offline · Changes stay in this form", systemImage: "wifi.slash")
                        Button(workspace.loading ? "Connecting…" : "Retry Connection") { Task { await workspace.refresh() } }
                            .disabled(workspace.loading)
                    }
                }
                if let errorMessage {
                    Section {
                        Text(errorMessage).foregroundStyle(.red)
                        if hasConflict {
                            Button("Reload Server Values") { confirmingReload = true }
                        }
                    }
                }
                content()
            }
            .disabled(workspace.saving || refreshing)
            .navigationTitle(title)
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { dismiss() }.disabled(workspace.saving || refreshing)
                }
                ToolbarItem(placement: .confirmationAction) {
                    if workspace.saving || refreshing {
                        ProgressView()
                    } else {
                        Button("Save") { Task { await submit() } }.disabled(hasConflict || !workspace.canWrite)
                    }
                }
            }
            .confirmationDialog("Replace Draft With Server Values?", isPresented: $confirmingReload) {
                Button("Reload", role: .destructive) { Task { await reloadDraft() } }
            } message: {
                Text("Reloading will discard the edits in this form.")
            }
        }
        .interactiveDismissDisabled()
    }

    private func submit() async {
        errorMessage = nil
        do { try await save() }
        catch {
            errorMessage = error.localizedDescription
            hasConflict = (error as? DashboardAPI.ServerError)?.status == 409
        }
    }

    private func reloadDraft() async {
        refreshing = true
        defer { refreshing = false }
        await workspace.refresh(replacingInFlight: true)
        if let error = workspace.connectionError {
            errorMessage = error
        } else {
            reload()
            errorMessage = nil
            hasConflict = false
        }
    }
}

struct OptionalDateField: View {
    let label: String
    @Binding var value: String

    var body: some View {
        if value.isEmpty {
            Button("Set \(label)") { value = dateString(.now) }
        } else {
            DatePicker(label, selection: Binding(
                get: { dateFormatter.date(from: value) ?? .now },
                set: { value = dateString($0) }
            ), displayedComponents: .date)
            Button("Clear \(label)", role: .destructive) { value = "" }
        }
    }
}

private var dateFormatter: DateFormatter {
    let formatter = DateFormatter()
    formatter.locale = Locale(identifier: "en_US_POSIX")
    formatter.calendar = Calendar(identifier: .gregorian)
    formatter.dateFormat = "yyyy-MM-dd"
    return formatter
}

func dateString(_ date: Date) -> String {
    dateFormatter.string(from: date)
}

func displayTimestamp(_ value: String) -> String {
    if value.count == 10, let day = dateFormatter.date(from: value) {
        return day.formatted(date: .abbreviated, time: .omitted)
    }
    let iso = ISO8601DateFormatter()
    iso.formatOptions.insert(.withFractionalSeconds)
    let fractional = iso.date(from: value)
    iso.formatOptions.remove(.withFractionalSeconds)
    guard let timestamp = fractional ?? iso.date(from: value) else { return value }
    return timestamp.formatted(date: .abbreviated, time: .shortened)
}
