import Foundation

struct Dashboard: Decodable {
    var jobs: [Job]
    let savedSearches: [SavedSearch]?
    let matchAlerts: [MatchAlert]?
    let unreadMatchCount: Int?
    let runs: [SearchRun]
    let statuses: [String]
    let running: Bool
    let preferences: Preferences
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
    struct Recruiter: Decodable {
        let resumeMatches: [String]
        let selectedWithoutEvidence: [String]
        let preparation: [String]
        let unknowns: [String]
        let hardRequirements: [String]
        let preferences: [String]
        let linkStatus: String
        let adviceMethod: String
    }
    let recruiter: Recruiter?
    var interest: Interest?
    let matchedSkills: [String]?
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
    let explanation: String?
    let applicationEvidence: String?
    let source: String?
    let posted: String?
    let lastVerified: String?
    let created: String
    let updated: String
    let url: String?
    let score: Int
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

    var concisePay: String {
        guard salaryCurrency == "USD", salaryPeriod == "year", salaryType == "base",
              let maximum = salaryMax else {
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

    var postingURL: URL? { url.flatMap(DashboardAPI.webURL) }

    var trackingStage: JobBucket? {
        switch bucket {
        case .archive: return .archive
        case .applied: return .applied
        case .interviews: return .interviews
        case .offers: return .offers
        default:
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
    var resumeEvidence: [String: String]?
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

struct SearchRun: Decodable, Identifiable {
    let id: Int
    let started: String
    let finished: String?
    let state: String
    let report: Report

    struct Report: Decodable {
        let newQualified: Int?
        let newReview: Int?
        let reverified: Int?
        let newlyClosed: Int?
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

enum DashboardAPI {
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

    static func dashboard(at address: String) async throws -> Dashboard {
        let data = try await request("/api/v1/dashboard", at: address)
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(Dashboard.self, from: data)
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
        var request = URLRequest(url: url, timeoutInterval: path.hasSuffix("/ai-review") ? 105 : 15)
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
