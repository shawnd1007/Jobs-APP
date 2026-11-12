import XCTest

final class JobsSearchUITests: XCTestCase {
    @MainActor
    func testSampleBrowseFiltersAndOffersLiveConnection() {
        continueAfterFailure = false
        let app = XCUIApplication()
        app.launchArguments = ["-backendURL", ""]
        app.launch()

        XCTAssertTrue(app.buttons["Explore sample jobs"].waitForExistence(timeout: 12))
        app.buttons["Explore sample jobs"].tap()
        app.tabBars.buttons["Browse"].tap()
        let filter = app.textFields["listingFilter"]
        XCTAssertTrue(filter.waitForExistence(timeout: 7))
        filter.tap()
        filter.typeText("harbor wren reconciliation\n")
        XCTAssertTrue(app.staticTexts["All Listings · 1"].waitForExistence(timeout: 7))
        XCTAssertTrue(app.staticTexts["Payments Reconciliation Analyst"].exists)

        app.buttons["Clear search"].tap()
        XCTAssertTrue(app.staticTexts["All Listings · 16"].waitForExistence(timeout: 7))
        app.buttons["Connect for Live Search"].tap()
        XCTAssertTrue(app.navigationBars["Server Settings"].waitForExistence(timeout: 7))
        XCTAssertFalse(app.buttons["Run Employer Search"].exists)
    }

    @MainActor
    func testConnectedBrowseCanFindNewEmployerListings() {
        continueAfterFailure = false
        let app = XCUIApplication()
        app.launchArguments = ["-backendURL", "http://127.0.0.1:18085"]
        app.launch()

        XCTAssertTrue(app.tabBars.buttons["Browse"].waitForExistence(timeout: 15))
        app.tabBars.buttons["Browse"].tap()
        let filter = app.textFields["listingFilter"]
        XCTAssertTrue(filter.waitForExistence(timeout: 7))
        filter.tap()
        filter.typeText("billing\n")
        XCTAssertTrue(app.staticTexts["All Listings · 1"].waitForExistence(timeout: 7))
        XCTAssertTrue(app.staticTexts["Billing Analyst"].exists)
        XCTAssertFalse(app.staticTexts["Payment Operations Specialist"].exists)
        app.buttons["Clear search"].tap()

        app.buttons["Find New Jobs"].tap()
        let run = app.buttons["Run Employer Search"]
        XCTAssertTrue(run.waitForExistence(timeout: 8))
        run.tap()
        XCTAssertTrue(app.staticTexts["fictional-slow"].waitForExistence(timeout: 8))
        let outcome = app.staticTexts["searchOutcome"]
        XCTAssertTrue(outcome.waitForExistence(timeout: 15))
        XCTAssertTrue(outcome.label.contains("incomplete checks"))
        XCTAssertTrue(outcome.label.contains("1 new listing saved"))
        XCTAssertTrue(run.isEnabled)
        run.tap()
        let retryFinished = XCTNSPredicateExpectation(
            predicate: NSPredicate(format: "label CONTAINS %@", "No new listings matched"), object: outcome)
        XCTAssertEqual(XCTWaiter.wait(for: [retryFinished], timeout: 15), .completed)
        XCTAssertTrue(run.isEnabled)
        app.tabBars.buttons["Browse"].tap()
        let posting = app.staticTexts["Payment Operations Specialist"]
        XCTAssertTrue(posting.waitForExistence(timeout: 25))
        XCTAssertTrue(app.staticTexts["All Listings · 3"].exists)
        posting.tap()
        let checkedLink = app.descendants(matching: .any)
            .matching(NSPredicate(format: "label == %@", "Open checked employer posting")).firstMatch
        XCTAssertTrue(checkedLink.waitForExistence(timeout: 8))
        let directEvidence = app.descendants(matching: .any).matching(identifier: "directPostingChecked").firstMatch
        for _ in 0..<4 {
            if directEvidence.exists { break }
            app.swipeUp()
        }
        XCTAssertTrue(directEvidence.exists)
        XCTAssertFalse(app.descendants(matching: .any).matching(identifier: "applicationFormChecked").firstMatch.exists)
    }
    @MainActor
    func testTrackingExternalApplicationWithoutLink() {
        continueAfterFailure = false
        let app = XCUIApplication()
        app.launchArguments = ["-backendURL", "http://127.0.0.1:18085"]
        app.launch()

        XCTAssertTrue(app.tabBars.buttons["My Jobs"].waitForExistence(timeout: 15))
        app.tabBars.buttons["My Jobs"].tap()
        let add = app.buttons["Add Application"]
        XCTAssertTrue(add.waitForExistence(timeout: 8))
        add.tap()
        let save = app.buttons["Save"]
        XCTAssertFalse(save.isEnabled)
        let title = app.textFields["Job title"]
        title.tap()
        title.typeText("Payroll Coordinator")
        let employer = app.textFields["Employer"]
        employer.tap()
        employer.typeText("Fictional Wren")
        save.tap()

        let listing = app.staticTexts["Payroll Coordinator"]
        XCTAssertTrue(listing.waitForExistence(timeout: 12))
        listing.tap()
        XCTAssertTrue(app.staticTexts["You entered these details. Jobs hasn’t verified the posting."]
            .waitForExistence(timeout: 8))
        XCTAssertFalse(app.buttons["Open saved link"].exists)
        XCTAssertFalse(app.staticTexts["Why It Matches"].exists)
        app.terminate()
        app.launch()
        XCTAssertTrue(app.tabBars.buttons["My Jobs"].waitForExistence(timeout: 15))
        app.tabBars.buttons["My Jobs"].tap()
        let stage = app.descendants(matching: .any).matching(identifier: "applicationStage").firstMatch
        XCTAssertTrue(stage.waitForExistence(timeout: 8))
        stage.tap()
        let applied = app.buttons.matching(NSPredicate(format: "label BEGINSWITH %@", "Applied (")).firstMatch
        XCTAssertTrue(applied.waitForExistence(timeout: 8))
        applied.tap()
        XCTAssertTrue(listing.waitForExistence(timeout: 8))
    }
}
