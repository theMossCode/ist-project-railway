function showModal(modal_id) {
    let modal = UIkit.modal("#" + modal_id);
    if (modal === undefined) {
        return false;
    }

    modal.show();
}

function hideModal(modal_id) {
    let _modal_id = "#" + modal_id;
    let modal = UIkit.modal(_modal_id);
    if (modal === undefined) {
        console.log("Element not found " + _modal_id);
        return false;
    }

    console.log("Hide " + _modal_id);
    modal.hide();
    setTimeout(() => {
        window.document.getElementById(modal_id).innerHTML = "";
    }, 200);
}

function afterSwapEvtListener(e) {
    if (e.detail.xhr.status != 201) {
    	console.log("Swapped " + e.detail.target.id);
        switch (e.detail.target.id) {
            case "new-project-dialog":
                showModal("new-project-dialog");
                return;
            case "new-topic-dialog":
                showModal("new-topic-dialog");
                return;
            case "new-dataobject-dialog":
            	showModal("new-dataobject-dialog");
            	break;
            case "edit-dataobject-dialog":
            	showModal("edit-dataobject-dialog");
            	break;
            default:
                return;
        }
    }
    // else if(e.detail.xhr.status == 201){
    // 	// Reload window
    // 	window.location.reload();
    // }
}

function beforeSwapEvtListener(e) {
    // If request was successful, fill #div-projects with resp data
    if (e.detail.xhr.status == 201) {
        console.log("created " + e.detail.elt.id + " " + e.detail.xhr.response);
        switch (e.detail.elt.id) {
            case "new-project-dialog":
                hideModal("new-project-dialog");
                window.location.reload();
                break;
            case "new-topic-dialog":
            	hideModal("new-topic-dialog");
            	window.location.reload();
            	break;
            case "new-dataobject-dialog":
            	hideModal("new-dataobject-dialog");
            	window.location.reload();
            	break;
            case "edit-dataobject-dialog":
            	hideModal("edit-dataobject-dialog");
            	window.location.reload();
            	break;
            default:
                // statements_def
                break;
        }
    }
}

;
(function initEventListeners() {
    htmx.on("htmx:afterSwap", afterSwapEvtListener);
    htmx.on("htmx:beforeSwap", beforeSwapEvtListener);
})()