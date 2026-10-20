# Ticket workspace

Open **http://127.0.0.1:8000/** after starting the existing local server. This is the main interface for trying the model. The API reference remains available at **/docs**.

![Desktop workspace showing the account-access example](images/workspace.png)

## Update an existing local installation

In the terminal running the server, press Ctrl+C. From the repository directory, with the support-ticket-ai environment active, run:

```bat
git pull --ff-only
python -m support_ticket_ai.serve --model-dir artifacts/demo-v1/model
```

Open http://127.0.0.1:8000/ and refresh if necessary. Your existing model bundle works with the new interface. No additional dependencies, JavaScript build tools, dataset download, or retraining are required for this interface update.

If Git reports local changes, preserve them and resolve the update before restarting; do not discard files just to make the pull succeed.

## Use the workspace

1. Wait for **Model ready**. If unavailable, check that the server has loaded the trained model and select **Check again**.
2. Enter a support request, or choose **Account access**, **Payment issue**, or **Order tracking**. Examples fill the editor; they do not automatically submit a request.
3. Select **Suggest category**. The editor is locked while a prediction is pending to keep the result associated with the submitted message.
4. Review the suggested category and its uncalibrated model score. Every result requires human review.
5. Expand **View API response** to inspect the actual JSON returned by the prediction endpoint.

Editing the message clears the displayed suggestion so an older result cannot be mistaken for the current request. Clear removes the editor contents and resets the result view. Requests are limited to 2,000 Unicode characters; whitespace-only input is not submitted.

The payment example deliberately includes the previously documented duplicate-charge failure. Its actual model suggestion is displayed, even when the suggestion is wrong. The interface does not substitute expected answers for predictions.

## Result interpretation

- **Suggested category:** the category with the highest score from the existing model.
- **Model score:** the original uncalibrated score, displayed to three decimal places. It is not a verified probability of correctness.
- **Human review required:** the final routing decision remains with a person.

The offline temperature-scaling experiment is not applied to these live scores. API version 0.2.0 adds an optional abstention outcome to POST /predict.

## Optional: No reliable suggestion

The [experimental abstention guide](11-experimental-abstention.md) explains evaluating and installing a model-bound score policy. With it enabled, low-scoring requests display **No reliable suggestion**, with instructions to classify them manually. This does not prove a request is unsupported; some valid requests are also withheld. The policy is opt-in and is loaded when the server starts. Human review remains required for both decisions.

## Availability, privacy, and layout

The page checks model readiness on opening, on retry, and every 30 seconds. Missing models, rejected requests, lost connections, and timeouts produce inline feedback. A request timeout is 15 seconds.

The application does not keep ticket history in browser storage. Ticket text is sent to the same local server that serves the page. The assets are bundled with the Python application; the workspace does not load remote fonts or a frontend framework from a CDN.

The layout adapts from a desktop editor/result split to stacked cards on smaller screens. It includes labelled form controls, keyboard focus styles, a skip link, reduced-motion support, and model-status feedback. These features are not a claim of a complete accessibility audit.

## Implementation and verification

Files:

- support_ticket_ai/web/index.html — structure and form labels
- support_ticket_ai/web/styles.css — layout and visual styling
- support_ticket_ai/web/app.js — readiness checks, form state, requests, and result rendering
- support_ticket_ai/api.py — workspace route and local asset serving

The new root route and assets are checked by API tests, including the model-unavailable state. All 51 Python tests pass locally. Browser checks passed at 1440, 900, 768, and 390 pixels, including real-model predictions, loading and disabled controls, example filling, character limits, Unicode counting, stale-result reset, JSON expansion, unavailable-model retry, and text-only rendering of response values. No JavaScript page errors or horizontal overflow were observed in those checks.

## Learning point

The browser gathers the message and sends JSON to the backend. The backend validates it and calls the saved model. JavaScript then renders the returned suggestion using textContent. Styling changes how the result is presented; they do not retrain the classifier or improve its predictive accuracy.
