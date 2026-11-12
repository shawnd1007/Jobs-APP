import Foundation

struct Dashboard: Decodable {
    var jobs: [Job]
    let savedSearches: [SavedSearch]?
    let matchAlerts: [MatchAlert]?
    let unreadMatchCount: Int?
    let runs: [SearchRun]
    let statuses: [String]
    let running: Bool
    var externalApplicationTracking: Bool? = nil
    var applicationPrepAvailable: Bool? = nil
    var preferences: Preferences
    let preferencesRevision: String
    let sources: [EmployerSource]
    let aiConfigured: Bool
    let aiAttemptsToday: Int
}

struct Job: Decodable, Identifiable {
    struct Interest: Codable {
        let state: String
        let version: Int
        let updated: String
    }
    struct ScoreBreakdown: Decodable {
        let targetRole: Int
        let selectedSkills: Int
        let skillGroups: Int
    }

    struct DutyEvidence: Decodable {
        let skill: String
        let duty: String
    }

    var dutyEvidence: [DutyEvidence]? = nil
    var matchedDutyCount: Int? = nil
    var scoreBreakdown: ScoreBreakdown? = nil
    var applicationVerified: String? = nil
    var postingVerified: String? = nil
    var postingVerificationExpires: String? = nil
    var externalApplication: Bool? = nil
    var interest: Interest?
    var matchedSkills: [String]?
    let matchedGroups: [String]?
    let matchGaps: [String]?
    let salaryMin: Double?
    let salaryCurrency: String?
    let salaryPeriod: String?
    let salaryType: String?
    let stale: Bool?
    let id: Int
    let title: String
    let employer: String
    let location: String?
    let locationEligibility: String?
    let locationReason: String?
    let area: String?
    let category: String?
    let salaryText: String?
    let salaryMax: Double?
    let availability: String?
    let description: String?
    var explanation: String?
    let applicationEvidence: String?
    let source: String?
    let posted: String?
    let lastVerified: String?
    let created: String
    let updated: String
    let url: String?
    var score: Int
    let matchLabel: String
    let queue: String?
    let reviewDecision: String
    let reviewBlockers: [String]
    let reviewChecks: [String: Bool]
    let reviewNote: String
    let reviewReviewer: String
    let reviewVersion: Int
    var status: String
    var applicationDate: String
    var followUp: String
    var notes: String
    var version: Int
    let aiAdvice: SavedAdvice?

    var publishedPay: String {
        guard let salaryText, !salaryText.isEmpty else { return "Not published" }
        return salaryText
    }

    var publishedAnnualBaseMax: Double? {
        guard salaryCurrency == "USD", salaryPeriod == "year", salaryType == "base" else { return nil }
        return salaryMax
    }

    var workSetting: String? {
        if ["Remote", "Hybrid", "On-site"].contains(area ?? "") { return area }
        let text = location?.lowercased() ?? ""
        if text.contains("hybrid") { return "Hybrid" }
        if text.contains("remote") { return "Remote" }
        if locationEligibility == "Eligible", !text.isEmpty { return "On-site" }
        return nil
    }

    var concisePay: String {
        guard let maximum = publishedAnnualBaseMax else {
            let text = publishedPay
            if text.localizedCaseInsensitiveContains("tier") { return "Published pay varies by tier" }
            return text.count > 110 ? "See employer pay details" : text
        }
        let currency = FloatingPointFormatStyle<Double>.Currency(code: "USD").precision(.fractionLength(0))
        if let minimum = salaryMin, minimum != maximum {
            return "\(minimum.formatted(currency))–\(maximum.formatted(currency)) annual base"
        }
        let prefix = salaryMin == nil ? "Up to " : ""
        return "\(prefix)\(maximum.formatted(currency)) annual base"
    }

    var isExternalApplication: Bool { externalApplication == true }

    var hasVerifiedPostingLink: Bool {
        guard availability == "Open", let postingVerificationExpires,
              let expires = ISO8601DateFormatter().date(from: postingVerificationExpires)
        else { return false }
        return expires >= .now
    }

    var postingURL: URL? { url.flatMap(DashboardAPI.webURL) }

    var trackingStage: JobBucket? {
        switch bucket {
        case .archive: return .archive
        case .applied: return .applied
        case .interviews: return .interviews
        case .offers: return .offers
        default:
            if isExternalApplication { return .all }
            if interest?.state == "passed" { return .archive }
            if interest?.state == "saved" || bucket == .ready || bucket == .hold { return .all }
            return nil
        }
    }

    func needsFollowUp(on day: String) -> Bool {
        trackingStage != .archive && !followUp.isEmpty && followUp <= day
    }

    var bucket: JobBucket? {
        if availability == "Closed" || ["Rejected", "Withdrawn", "Position Closed"].contains(status) {
            return .archive
        }
        if status == "Offer Received" { return .offers }
        if status.hasPrefix("Interview") { return .interviews }
        if ["Applied", "Assessment Received"].contains(status) { return .applied }
        if reviewDecision == "Dismissed" { return .archive }
        if locationEligibility == "Rejected" || queue == "Excluded" { return nil }
        if reviewDecision == "Hold" { return .hold }
        if reviewDecision == "Approved", reviewBlockers.isEmpty,
           ["Not Applied", "Planning to Apply", "Needs Verification"].contains(status) {
            return .ready
        }
        return .review
    }
}

enum JobBucket: String, CaseIterable, Identifiable {
    case review = "Review Inbox"
    case ready = "Ready to Apply"
    case applied = "Applied"
    case interviews = "Interviews"
    case offers = "Offers"
    case hold = "On Hold"
    case archive = "Closed / Dismissed"
    case all = "All History"

    var id: Self { self }
}

struct Preferences: Codable {
    var preferredSkills: [String]?
    var targetLocations: [String]?
    var workplaceTypes: [String]?
    var profile: String
    var categories: [String]
    var salaryFloor: Int
    var salaryPolicy: String
    var excludedTitleTerms: [String]
    var skillGroups: [SkillGroup]
    var additionalBoards: [String: [String]]
    var additionalEmployerUrls: [String]
    var disabledSources: [String]
    var aiEnabled: Bool
    var aiModel: String
    var aiDailyLimit: Int
    var scheduleEnabled: Bool
    var scheduleHourUtc: Int
}

struct SkillGroup: Codable {
    let label: String
    let points: Int
    let terms: [String]
}

struct EmployerSource: Decodable, Identifiable {
    let source: String
    let state: String
    let checked: String
    let count: Int
    let error: String
    let disabled: Bool
    let kind: String

    var id: String { source }
}

struct SearchStatus: Decodable {
    struct Run: Decodable {
        struct Progress: Decodable {
            let stage: String
            let completed: Int?
            let total: Int?
            let source: String?

            var label: String {
                guard let completed, let total, total > 0 else { return stage + "…" }
                return "\(stage): \(completed) of \(total)"
            }
        }

        let id: Int
        let state: String
        let started: String
        let progress: Progress?
    }

    let running: Bool
    let run: Run?
}

struct SearchRun: Decodable, Identifiable {
    let id: Int
    let started: String
    let finished: String?
    let state: String
    let trigger: String?
    let report: Report

    var originLabel: String {
        if trigger == "scheduled" { return "Scheduled" }
        if trigger == "manual" { return "Manual" }
        return "Search"
    }

    struct Report: Decodable {
        let newQualified: Int?
        let newReview: Int?
        let reverified: Int?
        let newlyClosed: Int?
        let manualReview: Int?
        let duplicates: Int?
        let deferredCandidates: Int?
        let deferredSourceDetails: Int?
        let postingChecks: Int?
        let postingChecksDeferred: Int?
        let firecrawlRequests: Int?
        let firecrawlCreditsReported: Double?
        let failures: [String]?
        let log: [String]?
        let topNew: [Lead]?
        let unprocessedEmployerUrls: [String]?

        struct Lead: Decodable {
            let title: String
            let employer: String
            let url: String
        }
    }
}

struct SavedAdvice: Decodable {
    let advice: Advice
    let model: String
    let created: String
    let stale: Bool

    struct Advice: Decodable {
        let summary: String
        let strengths: [String]
        let gaps: [String]
        let questions: [String]
        let nextSteps: [String]
    }
}

struct ApplicationPrep: Decodable {
    struct Example: Decodable {
        let skill: String
        let duty: String
        let profileExcerpt: String
    }

    let draft: String
    let version: Int
    let updated: String?
    let examples: [Example]
    let skillsToDocument: [String]
    let qualificationChecks: [String]
    let hasProfile: Bool
    let hasDescription: Bool
}

struct SavedApplicationDraft: Decodable {
    let draft: String
    let version: Int
    let updated: String
}

enum DashboardAPI {
    struct Snapshot {
        let dashboard: Dashboard
        let data: Data
        let syncedAt: Date
    }

    struct ServerError: LocalizedError {
        let status: Int
        let message: String
        var errorDescription: String? { message }
    }

    private struct ErrorBody: Decodable { let error: String }

    static func webURL(_ address: String) -> URL? {
        let trimmed = address.trimmingCharacters(in: .whitespacesAndNewlines)
        guard let parts = URLComponents(string: trimmed),
              let scheme = parts.scheme?.lowercased(),
              ["http", "https"].contains(scheme),
              let host = parts.host, !host.isEmpty,
              parts.user == nil, parts.password == nil else { return nil }
        return parts.url
    }

    static func endpoint(_ path: String, at address: String) -> URL? {
        guard let base = webURL(address),
              var parts = URLComponents(url: base, resolvingAgainstBaseURL: false),
              parts.query == nil, parts.fragment == nil else { return nil }
        let prefix = parts.percentEncodedPath
        parts.percentEncodedPath = (prefix.hasSuffix("/") ? String(prefix.dropLast()) : prefix) + path
        return parts.url
    }

    static func serverAddress(_ input: String) -> String? {
        let trimmed = input.trimmingCharacters(in: .whitespacesAndNewlines)
        let suppliedScheme = trimmed.contains("://")
        guard let url = webURL(suppliedScheme ? trimmed : "http://" + trimmed),
              var parts = URLComponents(url: url, resolvingAgainstBaseURL: false),
              parts.query == nil, parts.fragment == nil else { return nil }
        if !suppliedScheme && parts.port == nil { parts.port = 8084 }
        guard parts.port.map({ (1...65_535).contains($0) }) ?? true else { return nil }
        parts.scheme = parts.scheme?.lowercased()
        parts.host = parts.host?.lowercased()
        if parts.percentEncodedPath.hasSuffix("/") { parts.percentEncodedPath.removeLast() }
        return parts.string
    }

    static func load(at address: String) async throws -> Snapshot {
        let data = try await request("/api/v1/dashboard", at: address)
        return try snapshot(from: data, syncedAt: .now)
    }

    static func searchStatus(at address: String) async throws -> SearchStatus {
        let data = try await request("/api/v1/search-status", at: address)
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(SearchStatus.self, from: data)
    }

    static func applicationPrep(jobID: Int, at address: String) async throws -> ApplicationPrep {
        let data = try await request("/api/jobs/\(jobID)/application-prep", at: address)
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(ApplicationPrep.self, from: data)
    }

    static func saveApplicationDraft(jobID: Int, draft: String, version: Int,
                                     at address: String) async throws -> SavedApplicationDraft {
        struct Change: Encodable {
            let draft: String
            let version: Int
        }
        let body = try JSONEncoder().encode(Change(draft: draft, version: version))
        let data = try await request("/api/jobs/\(jobID)/application-prep", at: address, body: body)
        return try JSONDecoder().decode(SavedApplicationDraft.self, from: data)
    }

    fileprivate static func snapshot(from data: Data, syncedAt: Date) throws -> Snapshot {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try Snapshot(dashboard: decoder.decode(Dashboard.self, from: data), data: data, syncedAt: syncedAt)
    }

    static func connectionMessage(for error: Error) -> String {
        if error is DecodingError { return "This address didn’t return a compatible Jobs workspace." }
        if error is URLError { return "Check that your Mac is awake, the Jobs server is running, and this device can reach it." }
        return error.localizedDescription
    }

    @MainActor
    static func post<T: Encodable>(_ path: String, at address: String, body: T) async throws {
        let encoder = JSONEncoder()
        encoder.keyEncodingStrategy = .convertToSnakeCase
        _ = try await request(path, at: address, body: encoder.encode(body))
    }

    private static func request(_ path: String, at address: String, body: Data? = nil) async throws -> Data {
        guard let url = endpoint(path, at: address) else {
            throw ServerError(status: 0, message: "Check the URL in Server Settings.")
        }
        var request = URLRequest(url: url, timeoutInterval: path.hasSuffix("/ai-review") ? 105 : (path.hasSuffix("/search-status") ? 5 : 15))
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        if let body {
            request.httpMethod = "POST"
            request.httpBody = body
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
            request.setValue("dashboard", forHTTPHeaderField: "X-Jobs-Client")
        }

        let (data, response) = try await session.data(for: request)
        guard let response = response as? HTTPURLResponse else {
            throw ServerError(status: 0, message: "The server returned an invalid response.")
        }
        guard (200..<300).contains(response.statusCode) else {
            let detail = try? JSONDecoder().decode(ErrorBody.self, from: data)
            let fallback = path == "/api/run" && response.statusCode == 409
                ? "A search is already running." : "The server returned HTTP \(response.statusCode)."
            throw ServerError(status: response.statusCode, message: detail?.error ?? fallback)
        }
        return data
    }

    private final class NoRedirects: NSObject, URLSessionTaskDelegate {
        func urlSession(_ session: URLSession, task: URLSessionTask,
                        willPerformHTTPRedirection response: HTTPURLResponse,
                        newRequest request: URLRequest) async -> URLRequest? { nil }
    }

    private static let session = URLSession(configuration: .ephemeral, delegate: NoRedirects(), delegateQueue: nil)
}

enum OfflineWorkspace {
    private struct Stored: Codable {
        let address: String
        let syncedAt: Date
        let data: Data
    }

    static func load(for address: String) -> DashboardAPI.Snapshot? {
        guard let url = try? storageURL(), let data = try? Data(contentsOf: url),
              let stored = try? JSONDecoder().decode(Stored.self, from: data), stored.address == address else { return nil }
        return try? DashboardAPI.snapshot(from: stored.data, syncedAt: stored.syncedAt)
    }

    static func save(_ snapshot: DashboardAPI.Snapshot, for address: String) throws {
        let stored = Stored(address: address, syncedAt: snapshot.syncedAt, data: snapshot.data)
        try JSONEncoder().encode(stored).write(to: storageURL(), options: [.atomic, .completeFileProtection])
    }

    static func remove() throws {
        let url = try storageURL()
        if FileManager.default.fileExists(atPath: url.path) { try FileManager.default.removeItem(at: url) }
    }

    private static func storageURL() throws -> URL {
        var folder = try FileManager.default.url(for: .applicationSupportDirectory, in: .userDomainMask,
                                                appropriateFor: nil, create: true).appendingPathComponent("OfflineWorkspace")
        try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
        var values = URLResourceValues()
        values.isExcludedFromBackup = true
        try folder.setResourceValues(values)
        return folder.appendingPathComponent("snapshot.json")
    }
}

struct SavedSearch: Decodable, Identifiable {
    let id: Int
    let version: Int
    let name: String
    let skills: [String]
    let titleTerms: [String]?
    let locations: [String]
    let workplaceTypes: [String]
    let salaryMin: Int
    let salaryMax: Int?
    let enabled: Bool
}

struct MatchAlert: Decodable, Identifiable {
    let id: Int
    let jobId: Int
    let searchName: String
    let created: String
    let unread: Bool
}
