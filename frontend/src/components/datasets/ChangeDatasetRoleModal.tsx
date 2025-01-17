import React, { useEffect, useState } from "react";
import { Alert, Autocomplete, Button, Collapse, Container, Dialog, DialogActions, DialogContent, DialogTitle, Divider, FormControl, IconButton, InputLabel, MenuItem, Select, TextField, Typography } from "@mui/material";
import {useParams} from "react-router-dom";
import { setDatasetUserRole } from "../../actions/dataset";
import { useDispatch } from "react-redux";
import CloseIcon from "@mui/icons-material/Close";


type ChangeDatasetRoleProps = {
    open: boolean,
    handleClose: any,
    datasetName: string,
	currentRole: string,
	currentUser: string;
}

export default function ChangeDatasetRoleModal(props: ChangeDatasetRoleProps) {
	const dispatch = useDispatch();

	const { open, handleClose, datasetName, currentRole , currentUser} = props;
	const {datasetId} = useParams<{ datasetId?: string }>();
	const [email, setEmail] = useState(currentUser);
	const [role, setRole] = useState(currentRole);
	const [showSuccessAlert, setShowSuccessAlert] = useState(false);

	const setUserRole = (datasetId: string, username: string, role: string) => dispatch(setDatasetUserRole(datasetId, username, role));

	// component did mount
	useEffect(() => {
		// listUsers();
	}, []);

	const onShare = () => {
		setUserRole(datasetId, email, role);
		setEmail("");
		setRole("viewer");
		setShowSuccessAlert(true);
	};

	return (
		<Container>
			<Dialog open={open} onClose={handleClose} fullWidth={true} maxWidth="md"
				sx={{
					".MuiPaper-root": {
						padding: "2em",
					},
				}}>
				<DialogTitle>Share dataset &apos;{datasetName}&apos;</DialogTitle>
				<Divider />
				<DialogContent>
					<Typography>Change role for user {currentUser}</Typography>
					<div style={{
						display: "flex",
						alignItems: "center"
					}}>
						<FormControl variant="outlined" sx={{ m: 1, minWidth: 120 }}>
							<InputLabel id="demo-simple-select-label">Status</InputLabel>
							<Select
								labelId="demo-simple-select-label"
								id="demo-simple-select"
								value={role}
								defaultValue={currentRole}
								label="Status"
								onChange={(event, value) => {
									setRole(event.target.value);
								}}
							>
								<MenuItem value="owner">Owner</MenuItem>
								<MenuItem value="editor">Editor</MenuItem>
								<MenuItem value="uploader">Uploader</MenuItem>
								<MenuItem value="viewer">Viewer</MenuItem>
							</Select>
						</FormControl>
					</div>
					<Button variant="contained" sx={{ marginTop: 1 }} onClick={onShare} disabled={(email.length > 0) ? false : true}>Share</Button>
					<Collapse in={showSuccessAlert}>
						<br/>
						<Alert
							severity="success"
							action={
								<IconButton
									aria-label="close"
									color="inherit"
									size="small"
									onClick={() => {
										setShowSuccessAlert(false);
									}}
								>
									<CloseIcon fontSize="inherit" />
								</IconButton>
							}
							sx={{ mb: 2 }}
						>
                        Successfully added role!
						</Alert>
					</Collapse>
				</DialogContent>
				<DialogActions>
					<Button onClick={handleClose}>Close</Button>
				</DialogActions>
			</Dialog>
		</Container>
	);
}
